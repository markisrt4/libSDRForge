"""!
@brief Conservative SAME header confirmation from demodulated bytes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .extract import parse_same_header
from .models import SameAlert

_HEADER = re.compile(
    rb"ZCZC-[A-Z]{3}-[A-Z]{3}-\d{6}(?:-\d{6})*\+\d{4}-\d{7}-[A-Z0-9/ ]{1,8}-"
)


@dataclass(frozen=True)
class SameMessages:
    """!
    @brief Provide SameMessages behavior.
    """

    alerts: tuple[SameAlert, ...]
    end_of_message: bool


def confirm_same_messages(data: bytes, *, min_repeats: int = 2) -> SameMessages:
    """!
    @brief Confirm identical headers repeated in one capture, never infer alerts.
    @param data The data value.
    @param min_repeats The min repeats value.
    @return The operation result.
    """
    if min_repeats < 2:
        raise ValueError("min_repeats must be at least 2")
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    counts: dict[bytes, int] = {}
    for match in _HEADER.finditer(data):
        counts[match.group()] = counts.get(match.group(), 0) + 1
    alerts = []
    for raw, count in counts.items():
        if count >= min_repeats:
            alert = parse_same_header(raw.decode("ascii"))
            if alert is not None:
                alerts.append(alert)
    return SameMessages(tuple(alerts), b"NNNN" in data)
