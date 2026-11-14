# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Non-decoding RDS traffic-service discovery from CRC-validated groups."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sdrforge.protocols.rds.rds_block_sync import RdsGroup


@dataclass(frozen=True)
class TmcDiscoveryStatus:
    pi: int | None
    total_groups: int
    group_8a_count: int
    group_3a_count: int
    group_0a_ta_count: int
    group_0a_tp_count: int
    group_counts: dict[str, int]
    raw_8a: tuple[tuple[int, int, int], ...]
    oda_app_ids: tuple[int, ...]
    tmc_aid_seen: bool


class TmcDiscovery:
    """Observe candidate TMC traffic groups without interpreting locations.

    Group 8A is the RDS-TMC message group. Group 3A can carry
    Open Data Applications signalling, including TMC service metadata.
    Presence of either does not prove that usable traffic data is available.
    """

    def __init__(self, *, max_raw_groups: int = 32) -> None:
        if max_raw_groups < 0:
            raise ValueError("max_raw_groups must be nonnegative")
        self._max_raw_groups = max_raw_groups
        self.reset()

    def reset(self) -> None:
        self._pi: int | None = None
        self._total = 0
        self._counts: Counter[str] = Counter()
        self._ta = 0
        self._tp = 0
        self._raw: list[tuple[int, int, int]] = []
        self._oda_app_ids: set[int] = set()

    def process(self, group: RdsGroup) -> None:
        if not isinstance(group, RdsGroup):
            raise TypeError("expected RdsGroup")
        # Recovered/soft groups are diagnostics, never trusted TMC evidence.
        if (group.synchronization != "strict" or group.corrected_bits
                or group.uncertain_bits):
            return
        if self._pi is not None and group.pi != self._pi:
            self.reset()
        self._pi = group.pi
        kind = (group.block_b >> 12) & 0xF
        version = "B" if group.block_b & 0x0800 else "A"
        key = f"{kind}{version}"
        self._counts[key] += 1
        self._total += 1
        if kind == 0:
            self._tp += bool(group.block_b & 0x0400)
            self._ta += bool(group.block_b & 0x0010)
        if key == "3A":
            # RDS 3A group block D carries the ODA Application ID.
            self._oda_app_ids.add(group.block_d)
        if key == "8A" and len(self._raw) < self._max_raw_groups:
            self._raw.append((group.block_b, group.block_c, group.block_d))

    @property
    def status(self) -> TmcDiscoveryStatus:
        return TmcDiscoveryStatus(
            pi=self._pi,
            total_groups=self._total,
            group_8a_count=self._counts["8A"],
            group_3a_count=self._counts["3A"],
            group_0a_ta_count=self._ta,
            group_0a_tp_count=self._tp,
            group_counts=dict(sorted(self._counts.items())),
            raw_8a=tuple(self._raw),
            oda_app_ids=tuple(sorted(self._oda_app_ids)),
            tmc_aid_seen=0xCD46 in self._oda_app_ids,
        )
