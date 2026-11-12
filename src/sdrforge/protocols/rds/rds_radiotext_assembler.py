# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Conservative experimental RDS 2A RadioText assembly."""
from __future__ import annotations

from dataclasses import dataclass

from sdrforge.protocols.rds.rds_block_sync import RdsGroup


@dataclass(frozen=True)
class RadioTextSnapshot:
    pi: int
    ab: int
    preview: str
    complete: bool
    terminator_seen: bool
    missing_segments: tuple[int, ...]
    conflicting_segments: tuple[int, ...]
    observations: int
    corrected_observations: int


class RdsRadioTextAssembler:
    """Assemble 2A segments; never silently choose conflicting text.

    Reset on PI or A/B change. CRC-recovered payloads remain experimental;
    structural completeness is not an assertion of RF correctness.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._key: tuple[int, int] | None = None
        self._segments: dict[int, set[str]] = {}
        self._observations = 0
        self._corrected = 0

    def process(self, group: RdsGroup) -> RadioTextSnapshot | None:
        b = group.block_b
        if (b >> 12) & 15 != 2 or b & 0x0800:
            return None
        key = (group.pi, (b >> 4) & 1)
        if key != self._key:
            self.reset()
            self._key = key
        segment = b & 15
        payload = bytes((group.block_c >> 8, group.block_c & 255,
                         group.block_d >> 8, group.block_d & 255)).decode("latin-1")
        self._segments.setdefault(segment, set()).add(payload)
        self._observations += 1
        self._corrected += int(group.corrected_bits > 0)
        return self.snapshot()

    def snapshot(self) -> RadioTextSnapshot | None:
        if self._key is None:
            return None
        chars: list[str | None] = [None] * 64
        conflicts = tuple(sorted(index for index, variants in self._segments.items()
                                 if len(variants) > 1))
        for index, variants in self._segments.items():
            if len(variants) == 1:
                fragment = next(iter(variants))
                chars[index * 4:index * 4 + 4] = list(fragment)
        terminator = next((i for i, char in enumerate(chars) if char == "\r"), None)
        end = terminator if terminator is not None else 64
        missing = tuple(i for i in range((end + 3) // 4)
                        if any(char is None for char in chars[i * 4:min(end, i * 4 + 4)]))
        preview = "".join(char if char is not None else "?" for char in chars[:end])
        return RadioTextSnapshot(
            self._key[0], self._key[1], preview,
            terminator is not None and not missing and not conflicts,
            terminator is not None, missing, conflicts,
            self._observations, self._corrected,
        )
