# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Conservative ordered ALERT-C multi-group candidate tracking.

A continuity index is not a message identifier. Without validated sequence
and termination semantics, candidates are NEVER promoted to complete events.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sdrforge.protocols.rds.alert_c_8a import AlertC8a


@dataclass
class MessageCandidate:
    pi: int
    continuity_index: int
    first: AlertC8a | None = None
    continuations: list[AlertC8a] = field(default_factory=list)
    first_repetitions: int = 0
    continuation_repetitions: int = 0
    ambiguous: bool = False
    status: str = "incomplete_unverified"

    def as_dict(self) -> dict:
        return {
            "pi": f"0x{self.pi:04X}",
            "continuity_index": self.continuity_index,
            "first_event_code_raw": self.first.event_code if self.first else None,
            "first_location_code_raw": self.first.location_code_raw if self.first else None,
            "continuation_payloads": [item.continuation_payload for item in self.continuations],
            "first_repetitions": self.first_repetitions,
            "continuation_repetitions": self.continuation_repetitions,
            "ambiguous": self.ambiguous,
            "status": self.status,
        }


class AlertCCandidateTracker:
    """Track received groups in arrival order without fabricating completeness."""

    def __init__(self) -> None:
        self._candidates: list[MessageCandidate] = []
        self._active: dict[tuple[int, int], MessageCandidate] = {}
        self.orphan_continuations = 0

    @property
    def candidates(self) -> tuple[MessageCandidate, ...]:
        return tuple(self._candidates)

    def process(self, message: AlertC8a) -> None:
        if message.kind not in ("multi_first", "multi_continuation"):
            return
        if message.continuity_index is None:
            return
        key = (message.pi, message.continuity_index)
        active = self._active.get(key)
        if message.kind == "multi_first":
            if active is not None and active.first is not None and (
                active.first.event_code == message.event_code
                and active.first.location_code_raw == message.location_code_raw
                and active.first.direction == message.direction
                and active.first.extent == message.extent
            ):
                active.first_repetitions += 1
                return
            if active is not None:
                active.ambiguous = True
                active.status = "superseded_unverified"
            candidate = MessageCandidate(message.pi, message.continuity_index, first=message)
            self._candidates.append(candidate)
            self._active[key] = candidate
            return
        if active is None:
            self.orphan_continuations += 1
            candidate = MessageCandidate(message.pi, message.continuity_index)
            self._candidates.append(candidate)
            self._active[key] = candidate
            active = candidate
        if any(item.continuation_payload == message.continuation_payload
               for item in active.continuations):
            active.continuation_repetitions += 1
        else:
            active.continuations.append(message)

    def summary(self) -> dict:
        return {
            "candidate_count": len(self._candidates),
            "orphan_continuations": self.orphan_continuations,
            "complete_verified": 0,
            "candidates": [item.as_dict() for item in self._candidates],
            "warning": "Candidates are not confirmed incidents. Sequence termination, event tables and encrypted locations remain unresolved.",
        }
