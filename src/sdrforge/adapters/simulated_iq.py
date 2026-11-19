# SPDX-License-Identifier: MIT
"""!
@brief Real-time synthetic FM IQ source for hardware-free integration tests.
"""
from __future__ import annotations

import time

import numpy as np

from sdrforge.interfaces.sdr_source_if import SdrSourceIf
from sdrforge.models.iq import IqBlock, SdrCapabilities


class SimulatedIqSource(SdrSourceIf):
    """!
    @brief Provide simulated iq source behavior.
    """
    def __init__(self, *, block_samples: int = 24_000) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param block_samples The ``block_samples`` value.
        """
        if block_samples < 2048:
            raise ValueError("block_samples must be at least 2048")
        self.block_samples = block_samples
        self.frequency_hz = 104_300_000
        self.sample_rate_hz = 2_400_000
        self._open = False
        self._running = False
        self._sample_index = 0
        self._next_read = 0.0

    def open(self) -> None:
        """!
        @brief Open the component.

        @param self The current instance.
        """
        self._open = True

    def close(self) -> None:
        """!
        @brief Close the component.

        @param self The current instance.
        """
        self._running = False
        self._open = False

    def is_connected(self) -> bool:
        """!
        @brief Return whether the connected.

        @param self The current instance.
        @return The operation result.
        """
        return self._open

    def get_capabilities(self) -> SdrCapabilities:
        """!
        @brief Return the capabilities.

        @param self The current instance.
        @return The operation result.
        """
        return SdrCapabilities(
            min_frequency_hz=87_500_000,
            max_frequency_hz=108_000_000,
            supported_sample_rates_hz=(2_400_000,),
        )

    def set_center_frequency(self, frequency_hz: int) -> None:
        """!
        @brief Set the center frequency.

        @param self The current instance.
        @param frequency_hz The frequency in hertz.
        """
        self.frequency_hz = frequency_hz

    def get_center_frequency(self) -> int:
        """!
        @brief Return the center frequency.

        @param self The current instance.
        @return The operation result.
        """
        return self.frequency_hz

    def get_sample_rate(self) -> int:
        """!
        @brief Return the sample rate.

        @param self The current instance.
        @return The operation result.
        """
        return self.sample_rate_hz

    def set_sample_rate(self, sample_rate_hz: int) -> None:
        """!
        @brief Set the sample rate.

        @param self The current instance.
        @param sample_rate_hz The sample rate in hertz.
        """
        if sample_rate_hz != 2_400_000:
            raise ValueError("simulated source requires 2.4 Msps")
        self.sample_rate_hz = sample_rate_hz

    def set_gain(self, gain_db: float | None) -> None:
        """!
        @brief Set the gain.

        @param self The current instance.
        @param gain_db The tuner gain in decibels, or ``None`` for automatic gain.
        """

    def start(self) -> None:
        """!
        @brief Start the component.

        @param self The current instance.
        """
        if not self._open:
            raise RuntimeError("source not opened")
        self._running = True
        self._sample_index = 0
        self._next_read = time.monotonic()

    def stop(self) -> None:
        """!
        @brief Stop the component.

        @param self The current instance.
        """
        self._running = False

    def read_iq(self) -> IqBlock:
        """!
        @brief Read iq.

        @param self The current instance.
        @return The operation result.
        """
        if not self._running:
            raise RuntimeError("source not started")
        now = time.monotonic()
        if self._next_read > now:
            time.sleep(self._next_read - now)
        self._next_read = max(self._next_read, time.monotonic()) + (
            self.block_samples / self.sample_rate_hz
        )
        indices = self._sample_index + np.arange(self.block_samples, dtype=np.float64)
        # Continuous phase: 20 kHz carrier offset, 1 kHz FM modulation.
        phase = (
            2.0 * np.pi * 20_000.0 * indices / self.sample_rate_hz
            - 50.0 * np.cos(2.0 * np.pi * 1000.0 * indices / self.sample_rate_hz)
        )
        iq = np.empty(self.block_samples * 2, dtype=np.uint8)
        iq[0::2] = np.clip(127.5 + 90.0 * np.cos(phase), 0, 255).astype(np.uint8)
        iq[1::2] = np.clip(127.5 + 90.0 * np.sin(phase), 0, 255).astype(np.uint8)
        self._sample_index += self.block_samples
        return IqBlock(
            samples=iq.tobytes(),
            center_frequency_hz=self.frequency_hz,
            sample_rate_hz=self.sample_rate_hz,
            timestamp_ns=time.monotonic_ns(),
        )
