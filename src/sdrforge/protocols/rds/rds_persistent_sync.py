# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Experimental streaming RDS framing consensus and strict group recovery.

A repeated CRC-valid A block at the same modulo-104 position and PI acquires
alignment. Damaged groups do not shift the frame. Only fully clean groups
are emitted to downstream metadata consumers.
"""
from __future__ import annotations

from collections import Counter, deque

import numpy as np

from sdrforge.protocols.rds.rds_block_sync import RdsGroup, decode_block


class RdsPersistentSynchronizer:
    def __init__(self, *, required_anchors: int = 2, loss_groups: int = 40) -> None:
        if required_anchors < 2 or loss_groups < 1:
            raise ValueError("invalid framing thresholds")
        self.required_anchors = required_anchors
        self.loss_groups = loss_groups
        self.reset()

    def reset(self) -> None:
        self._bits: list[int] = []
        self._valid: list[bool] = []
        self._base = 0
        self._seen = 0
        self._votes: Counter[tuple[int, int]] = Counter()
        self._recent_anchors: deque[tuple[int, tuple[int, int]]] = deque()
        self.alignment: int | None = None
        self.pi: int | None = None
        self.groups_found = 0
        self.clean_blocks = 0
        self.missing_blocks = 0
        self.partial_groups = 0
        self.loss_events = 0
        self._next_group: int | None = None
        self._groups_without_anchor = 0
        self.acquisition_events: list[dict[str, int | str]] = []
        self.loss_positions: list[int] = []
        self.last_alignment: int | None = None
        self.last_pi: int | None = None
        self.aligned_block_counts: Counter[str] = Counter()
        self._groups_without_evidence = 0

    @property
    def locked(self) -> bool:
        return self.alignment is not None

    @property
    def sync_confidence(self) -> int:
        if not self.locked:
            return 0
        return max(1, min(10, self.loss_groups - self._groups_without_anchor))

    def _word(self, pos: int) -> int | None:
        start = pos - self._base
        if start < 0 or start + 26 > len(self._bits):
            return None
        if not all(self._valid[start:start + 26]):
            return None
        word = 0
        for bit in self._bits[start:start + 26]:
            word = (word << 1) | bit
        return word

    def _block(self, pos: int, offset: str) -> tuple[str, int] | None:
        word = self._word(pos)
        return decode_block(word, offset) if word is not None else None

    def _expire_votes(self) -> None:
        # Votes represent recent acquisition evidence, not lifetime counts.
        cutoff = self._seen - 104 * self.loss_groups
        while self._recent_anchors and self._recent_anchors[0][0] < cutoff:
            _, key = self._recent_anchors.popleft()
            self._votes[key] -= 1
            if self._votes[key] <= 0:
                del self._votes[key]

    def process(self, bits: np.ndarray, valid: np.ndarray | None = None) -> list[RdsGroup]:
        values = np.asarray(bits)
        if values.ndim != 1 or not np.all((values == 0) | (values == 1)):
            raise ValueError("expected one-dimensional binary bits")
        flags = np.ones(len(values), dtype=np.bool_) if valid is None else np.asarray(valid)
        if flags.ndim != 1 or len(flags) != len(values):
            raise ValueError("valid mask must match bits")
        found: list[RdsGroup] = []
        for bit, ok in zip(values, flags):
            self._bits.append(int(bit))
            self._valid.append(bool(ok))
            self._seen += 1
            pos = self._seen - 26
            if pos >= 0:
                a = self._block(pos, "A")
                if a:
                    key = (pos % 104, a[1])
                    self._votes[key] += 1
                    self._recent_anchors.append((pos, key))
                    if not self.locked and self._votes[key] >= self.required_anchors:
                        self.alignment, self.pi = key
                        self.last_alignment, self.last_pi = key
                        self.acquisition_events.append({"bit": pos, "residue": key[0],
                                                        "pi": f"0x{key[1]:04X}"})
                        # Begin with the next complete group, avoiding replay of
                        # groups already consumed during acquisition.
                        self._next_group = pos
                        self._groups_without_anchor = 0
            self._expire_votes()
            while self.locked and self._next_group is not None and self._seen >= self._next_group + 104:
                start = self._next_group
                blocks = [self._block(start, "A"), self._block(start + 26, "B"),
                          self._block(start + 52, "C") or self._block(start + 52, "C_prime"),
                          self._block(start + 78, "D")]
                good = sum(block is not None for block in blocks)
                self.clean_blocks += good
                for name, block in zip(("A", "B", "C", "D"), blocks):
                    if block is not None:
                        self.aligned_block_counts[name] += 1
                self.missing_blocks += 4 - good
                if good and good < 4:
                    self.partial_groups += 1
                if blocks[0] and blocks[0][1] == self.pi:
                    self._groups_without_anchor = 0
                else:
                    self._groups_without_anchor += 1
                # Other CRC-valid aligned blocks support framing, but cannot
                # establish station identity or independently acquire lock.
                if (blocks[0] and blocks[0][1] == self.pi) or any(blocks[1:]):
                    self._groups_without_evidence = 0
                else:
                    self._groups_without_evidence += 1
                if good == 4 and blocks[0][1] == self.pi:
                    found.append(RdsGroup(blocks[0][1], blocks[1][1],
                                          blocks[2][1], blocks[3][1],
                                          blocks[2][0] == "C_prime"))
                    self.groups_found += 1
                self._next_group += 104
                if self._groups_without_evidence >= self.loss_groups:
                    self.loss_positions.append(start)
                    self.alignment = self.pi = self._next_group = None
                    self.loss_events += 1
                    self._groups_without_evidence = 0
                    self._votes.clear()
                    self._recent_anchors.clear()
            # Keep enough history for an in-progress group and sliding A scan.
            trim = max(0, len(self._bits) - 208)
            if trim:
                del self._bits[:trim]
                del self._valid[:trim]
                self._base += trim
        return found
