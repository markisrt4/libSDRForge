# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Conservative confirmation of repeated experimental RDS observations.

This is deliberately separate from the trusted receiver metadata path.
Each observation must come from a distinct 104-bit group position.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sdrforge.protocols.rds.rds_block_sync import RdsGroup


@dataclass(frozen=True)
class ConfirmedRdsFragment:
    pi: int
    ab_flag: int
    segment: int
    text: str
    observations: int


@dataclass(frozen=True)
class ExperimentalRadioText:
    """Provisional 2A text; '?' marks missing or conflicting segments."""
    pi: int | None
    ab_flag: int | None
    preview: str
    confirmed_segments: int
    missing_segments: tuple[int, ...]
    conflicted_segments: tuple[int, ...]
    complete: bool
    observations: tuple[int, ...]


class RdsSoftConfirmation:
    """Require independent matching 2A RadioText segments before publication.

    Conflicting values quarantine an address until reset, rather than letting
    an attacker or noisy station win by repeated votes. No TMC groups pass.
    """

    def __init__(self, *, repetitions: int = 2) -> None:
        if repetitions < 2:
            raise ValueError("soft confirmation requires at least two observations")
        self.repetitions = repetitions
        self.reset()

    def reset(self) -> None:
        self._epoch: tuple[int, int] | None = None
        self._seen: dict[int, set[int]] = defaultdict(set)
        self._values: dict[int, dict[str, int]] = defaultdict(dict)
        self._conflicted: set[int] = set()

    @property
    def radio_text(self) -> ExperimentalRadioText:
        chars = ["?"] * 64
        counts = [0] * 16
        missing = []
        for index in range(16):
            variants = self._values.get(index, {})
            if index in self._conflicted or len(variants) != 1:
                missing.append(index)
                continue
            fragment, count = next(iter(variants.items()))
            if count < self.repetitions:
                missing.append(index)
                continue
            chars[index * 4:index * 4 + 4] = list(fragment)
            counts[index] = count
        preview = "".join(chars)
        terminator = preview.find("\\r")
        if terminator >= 0:
            preview = preview[:terminator]
            required = set(range(terminator // 4 + 1))
        else:
            required = set(range(16))
        complete = not (required & set(missing))
        return ExperimentalRadioText(
            self._epoch[0] if self._epoch else None,
            self._epoch[1] if self._epoch else None,
            preview, sum(count > 0 for count in counts),
            tuple(missing), tuple(sorted(self._conflicted)),
            complete, tuple(counts))

    def observe(self, group: RdsGroup, *, start_bit: int,
                uncertain_bits: int) -> ConfirmedRdsFragment | None:
        if start_bit < 0 or uncertain_bits < 0 or uncertain_bits > 104:
            raise ValueError("invalid observation provenance")
        if (group.block_b >> 12) & 15 != 2 or group.block_b & 0x0800:
            return None
        ab = (group.block_b >> 4) & 1
        epoch = (group.pi, ab)
        if epoch != self._epoch:
            self.reset()
            self._epoch = epoch
        segment = group.block_b & 15
        if start_bit in self._seen[segment]:
            return None
        self._seen[segment].add(start_bit)
        text = "".join(chr((word >> shift) & 255)
                       for word in (group.block_c, group.block_d)
                       for shift in (8, 0))
        values = self._values[segment]
        values[text] = values.get(text, 0) + 1
        if len(values) > 1:
            self._conflicted.add(segment)
        if segment in self._conflicted or values[text] < self.repetitions:
            return None
        return ConfirmedRdsFragment(group.pi, ab, segment, text, values[text])
