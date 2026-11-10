# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Incremental RDS PI, Program Service and RadioText metadata assembly."""

from __future__ import annotations

from dataclasses import dataclass

from sdrforge.protocols.rds.rds_block_sync import RdsGroup


@dataclass(frozen=True)
class RdsMetadata:
    pi: int | None
    program_service: str | None
    radio_text: str | None


class RdsMetadataDecoder:
    """Decode group 0A/0B PS and group 2A/2B RadioText.

    Only complete segment sets are published. PI changes clear all cached
    station text; RadioText A/B flag changes clear the RT assembly.
    """

    def __init__(self, *, ps_repetitions: int = 1) -> None:
        if ps_repetitions < 1:
            raise ValueError("ps_repetitions must be positive")
        self._ps_repetitions = ps_repetitions
        self.reset()

    def reset(self) -> None:
        self._pi: int | None = None
        self._ps: list[str | None] = [None] * 4
        self._ps_candidates: list[str | None] = [None] * 4
        self._ps_counts = [0] * 4
        self._rt: list[str | None] = [None] * 16
        self._rt_ab: int | None = None
        self._rt_variant: int | None = None
        self._program_service: str | None = None
        self._radio_text: str | None = None

    def lose_sync(self) -> None:
        """Discard partial assemblies without erasing last-known station data."""
        self._ps = [None] * 4
        self._ps_candidates = [None] * 4
        self._ps_counts = [0] * 4
        self._rt = [None] * 16
        self._rt_ab = None
        self._rt_variant = None

    @property
    def metadata(self) -> RdsMetadata:
        return RdsMetadata(self._pi, self._program_service, self._radio_text)

    @staticmethod
    def _chars(word: int) -> str:
        return chr((word >> 8) & 0xFF) + chr(word & 0xFF)

    def process(self, group: RdsGroup) -> RdsMetadata:
        if not isinstance(group, RdsGroup):
            raise TypeError("expected an RdsGroup")
        if self._pi != group.pi:
            self.reset()
            self._pi = group.pi

        group_type = (group.block_b >> 12) & 0xF
        version_b = bool(group.block_b & 0x0800)

        if group_type == 0:
            index = group.block_b & 0x3
            value = self._chars(group.block_d)
            if value == self._ps_candidates[index]:
                self._ps_counts[index] += 1
            else:
                self._ps_candidates[index] = value
                self._ps_counts[index] = 1
            if self._ps_counts[index] >= self._ps_repetitions:
                self._ps[index] = value
            if all(segment is not None for segment in self._ps):
                self._program_service = "".join(self._ps).rstrip()

        elif group_type == 2:
            ab_flag = (group.block_b >> 4) & 1
            variant = 1 if version_b else 0
            if ab_flag != self._rt_ab or variant != self._rt_variant:
                self._rt = [None] * 16
                self._radio_text = None
                self._rt_ab = ab_flag
                self._rt_variant = variant
            index = group.block_b & 0xF
            if version_b:
                self._rt[index] = self._chars(group.block_d)
            else:
                self._rt[index] = (self._chars(group.block_c)
                                   + self._chars(group.block_d))
            # A carriage return terminates RadioText. Otherwise publish
            # only when all 16 segments have arrived.
            joined = ""
            for segment in self._rt:
                if segment is None:
                    break
                joined += segment
                if "\r" in segment:
                    self._radio_text = joined.split("\r", 1)[0].rstrip()
                    break
            else:
                if all(segment is not None for segment in self._rt):
                    self._radio_text = joined.rstrip()
        return self.metadata
