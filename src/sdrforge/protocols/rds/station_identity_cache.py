# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Confirm RDS station identity without reacting to one stray PI value."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StationIdentity:
    pi: int
    frequency_hz: int
    program_service: str | None = None


class StationIdentityCache:
    """Cache confirmed PI identity; require consecutive evidence for changes."""

    def __init__(self, confirmation_groups: int = 3) -> None:
        if confirmation_groups < 1:
            raise ValueError("confirmation_groups must be positive")
        self.confirmation_groups = confirmation_groups
        self.current: StationIdentity | None = None
        self._candidate: int | None = None
        self._candidate_count = 0

    def observe(self, pi: int, frequency_hz: int,
                program_service: str | None = None) -> str | None:
        """Return 'identified' or 'changed' only when identity is confirmed."""
        if not 0 <= pi <= 0xFFFF:
            raise ValueError("PI must be a 16-bit unsigned value")
        ps = program_service.strip() if program_service else None
        if self.current is not None and self.current.pi == pi:
            self._candidate = None
            self._candidate_count = 0
            self.current = StationIdentity(pi, frequency_hz, ps or self.current.program_service)
            return None
        if pi != self._candidate:
            self._candidate = pi
            self._candidate_count = 0
        self._candidate_count += 1
        if self._candidate_count < self.confirmation_groups:
            return None
        changed = self.current is not None
        self.current = StationIdentity(pi, frequency_hz, ps)
        self._candidate = None
        self._candidate_count = 0
        return "changed" if changed else "identified"
