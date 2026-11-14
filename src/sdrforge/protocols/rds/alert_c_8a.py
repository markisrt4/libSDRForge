# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Parse ALERT-C 8A transmission structure without decrypting traffic locations.

The X field is the low five bits of RDS block B. For traffic data
(X4=0), X3=1 denotes a single group, X3=0 denotes a multi-group.
In multi-group messages Y15 of block C identifies the first group.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from sdrforge.protocols.rds.rds_block_sync import RdsGroup


@dataclass(frozen=True)
class AlertC8a:
    pi: int
    kind: str
    continuity_index: int | None
    duration: int | None
    first_group: bool | None
    event_code: int | None
    location_code_raw: int | None
    direction: int | None
    extent: int | None
    diversion: bool | None
    continuation_payload: int | None
    synchronization: str


def parse_alert_c_8a(group: RdsGroup) -> AlertC8a | None:
    """Decode structure only; event labels and decrypted locations require tables.

    The raw location code is never assumed to be a usable map reference.
    Continuation payloads are uninterpreted 28-bit fragments.
    """
    b = group.block_b
    c = group.block_c
    d = group.block_d
    if (b >> 12) != 8 or b & 0x0800:
        return None
    x = b & 0x1F
    if x & 0x10:
        return AlertC8a(group.pi, "tuning", None, None, None, None, None,
                         None, None, None, None, group.synchronization)
    if x & 0x08:
        return AlertC8a(group.pi, "single", None, x & 7, True,
                         c & 0x7FF, d, (c >> 14) & 1, (c >> 11) & 7,
                         bool(c & 0x8000), None, group.synchronization)
    first = bool(c & 0x8000)
    return AlertC8a(
        group.pi, "multi_first" if first else "multi_continuation",
        x & 7, None, first, c & 0x7FF if first else None,
        d if first else None, (c >> 14) & 1 if first else None,
        (c >> 11) & 7 if first else None, None,
        None if first else ((c & 0x0FFF) << 16) | d,
        group.synchronization,
    )


def to_dict(message: AlertC8a) -> dict:
    return asdict(message)
