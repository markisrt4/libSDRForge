"""!
@brief Deterministic synthetic 1090 MHz complex IQ test vectors.
"""

from __future__ import annotations

import numpy as np


def synthesize_iq(
    frames: tuple[bytes, ...],
    sample_rate: float = 2e6,
    *,
    gap_us: float = 40,
    amplitude: float = 1.0,
    noise: float = 0.0,
    seed: int = 0,
) -> np.ndarray:
    """!
    @brief Handle synthesize iq.
    @param frames The frames value.
    @param sample_rate The sample rate value.
    @param gap_us The gap us value.
    @param amplitude The amplitude value.
    @param noise The noise value.
    @param seed The seed value.
    @return The operation result.
    """
    if sample_rate < 2e6 or gap_us < 0 or amplitude <= 0 or noise < 0:
        raise ValueError("invalid synthetic IQ parameters")
    if any(len(frame) != 14 for frame in frames):
        raise ValueError("expected 112-bit frames")
    total_us = 20 + len(frames) * (120 + gap_us) + 20
    length = int(np.ceil(total_us * sample_rate / 1e6))
    signal = np.zeros(length, dtype=np.complex64)

    def pulse(t: float) -> None:
        left = int(np.ceil(t * sample_rate / 1e6))
        right = int(np.ceil((t + 0.5) * sample_rate / 1e6))
        signal[left:right] = amplitude

    for index, frame in enumerate(frames):
        base = 20 + index * (120 + gap_us)
        for offset in (0, 1, 3.5, 4.5):
            pulse(base + offset)
        for bit_index, bit in enumerate(
            np.unpackbits(np.frombuffer(frame, dtype=np.uint8))
        ):
            pulse(base + 8 + bit_index + (0.0 if bit else 0.5))
    if noise:
        rng = np.random.default_rng(seed)
        signal += (
            noise * (rng.standard_normal(length) + 1j * rng.standard_normal(length))
        ).astype(np.complex64)
    return signal
