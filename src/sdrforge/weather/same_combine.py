"""!
@brief Experimental SAME repeated-burst recovery, never alert confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .same_messages import _HEADER


@dataclass(frozen=True)
class CombinedHeader:
    """!
    @brief Provide CombinedHeader behavior.
    """

    candidate: bytes
    support: tuple[int, ...]
    complete_header: bool
    verified: bool = False


def combine_same_bursts(
    bursts: tuple[bytes, ...] | list[bytes],
    *,
    confidences: tuple[np.ndarray, ...] | None = None,
) -> CombinedHeader:
    """!
    @brief Combine aligned candidate bytes using weighted bit voting.
    @param bursts The bursts value.
    @param confidences The confidences value.
    @return The operation result.
    """
    if len(bursts) < 3:
        raise ValueError("at least three bursts are required")
    if not all(isinstance(burst, bytes) for burst in bursts):
        raise TypeError("bursts must contain bytes")
    length = len(bursts[0])
    if not length or any(len(burst) != length for burst in bursts):
        raise ValueError("bursts must be nonempty and equally aligned")
    if confidences is None:
        weights = np.ones((len(bursts), length * 8), dtype=float)
    else:
        if len(confidences) != len(bursts):
            raise ValueError("one confidence array required per burst")
        weights = np.asarray(confidences, dtype=float)
        if (
            weights.shape != (len(bursts), length * 8)
            or not np.all(np.isfinite(weights))
            or np.any(weights < 0)
        ):
            raise ValueError(
                "confidence weights must be finite nonnegative per-bit arrays"
            )
    data = bytearray()
    support = []
    for byte_index in range(length):
        output = 0
        for bit in range(8):
            position = byte_index * 8 + bit
            ones = sum(
                float(weights[i, position])
                for i, burst in enumerate(bursts)
                if burst[byte_index] & (1 << bit)
            )
            zeros = sum(
                float(weights[i, position])
                for i, burst in enumerate(bursts)
                if not burst[byte_index] & (1 << bit)
            )
            if ones > zeros:
                output |= 1 << bit
            support.append(
                sum(
                    bool(burst[byte_index] & (1 << bit)) == (ones > zeros)
                    for burst in bursts
                )
            )
        data.append(output)
    candidate = bytes(data)
    return CombinedHeader(
        candidate, tuple(support), _HEADER.fullmatch(candidate) is not None
    )
