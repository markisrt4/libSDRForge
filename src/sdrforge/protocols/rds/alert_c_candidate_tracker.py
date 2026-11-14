# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Conservative ordered ALERT-C multi-group candidate tracking.

A continuity index is not a message identifier. Without validated sequence
and termination semantics, candidates are NEVER promoted to complete events.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Callable

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
    expected_groups: int | None = None
    next_sequence: int | None = None
    sequence_error: bool = False
    continuation_counts: dict[tuple, int] = field(default_factory=dict)
    last_seen: float = 0.0
    conflicting_fragments: int = 0

    def as_dict(self) -> dict:
        first_count = 1 + self.first_repetitions if self.first else 0
        fragment_counts = [self.continuation_counts.get(
            (item.group_sequence, item.second_group, item.continuation_payload), 0
        ) for item in self.continuations]
        complete = self.status == "structurally_complete_unverified"
        all_counts = [first_count, *fragment_counts]
        repetition = ("repeated_all_groups" if complete and all(n >= 2 for n in all_counts)
                      else "partial_repetition" if any(n >= 2 for n in all_counts)
                      else "single_observation")
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
            "expected_groups": self.expected_groups,
            "next_sequence": self.next_sequence,
            "sequence_error": self.sequence_error,
            "conflicting_fragments": self.conflicting_fragments,
            "structurally_complete": complete,
            "first_observations": first_count,
            "continuation_observations": fragment_counts,
            "repetition_confidence": repetition,
            "reception_verified": False,
            "traffic_event_verified": False,
            "location_resolution": "unresolved",
            "encrypted_service": None,
            "event_code_meaning": None,
            "usable_for_navigation": False,
        }


class AlertCCandidateTracker:
    """Track received groups in arrival order without fabricating completeness."""

    def __init__(self, *, max_candidates: int = 128,
                 candidate_ttl_seconds: float = 300.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        if candidate_ttl_seconds <= 0:
            raise ValueError("candidate_ttl_seconds must be positive")
        self._max_candidates = max_candidates
        self._ttl = candidate_ttl_seconds
        self._clock = clock
        self.expired_candidates = 0
        self._candidates: list[MessageCandidate] = []
        self._active: dict[tuple[int, int], MessageCandidate] = {}
        self.orphan_continuations = 0

    @property
    def candidates(self) -> tuple[MessageCandidate, ...]:
        return tuple(self._candidates)

    def expire(self) -> None:
        """Remove stale candidates, including active continuity-index mappings."""
        now = self._clock()
        stale = [item for item in self._candidates
                 if now - item.last_seen >= self._ttl]
        for item in stale:
            self._candidates.remove(item)
            key = (item.pi, item.continuity_index)
            if self._active.get(key) is item:
                del self._active[key]
        self.expired_candidates += len(stale)

    def process(self, message: AlertC8a) -> None:
        if message.kind not in ("multi_first", "multi_continuation"):
            return
        if message.continuity_index is None:
            return
        self.expire()
        now = self._clock()
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
                active.last_seen = now
                return
            if active is not None:
                active.ambiguous = True
                active.status = "superseded_unverified"
            candidate = MessageCandidate(message.pi, message.continuity_index, first=message, last_seen=now)
            self._append_candidate(candidate)
            self._active[key] = candidate
            return
        if active is None:
            self.orphan_continuations += 1
            candidate = MessageCandidate(message.pi, message.continuity_index, last_seen=now)
            self._append_candidate(candidate)
            self._active[key] = candidate
            active = candidate
        active.last_seen = now
        identity = (message.group_sequence, message.second_group, message.continuation_payload)
        active.continuation_counts[identity] = active.continuation_counts.get(identity, 0) + 1
        if any(
            item.continuation_payload == message.continuation_payload
            and item.second_group == message.second_group
            and item.group_sequence == message.group_sequence
            for item in active.continuations
        ):
            active.continuation_repetitions += 1
            return
        if any(item.group_sequence == message.group_sequence
               and item.second_group == message.second_group
               and item.continuation_payload != message.continuation_payload
               for item in active.continuations):
            active.conflicting_fragments += 1
            active.sequence_error = True
        if active.first is None:
            active.sequence_error = True
        if message.second_group:
            if active.continuations:
                active.sequence_error = True
            if message.group_sequence is not None:
                active.expected_groups = message.group_sequence + 2
                active.next_sequence = message.group_sequence - 1 if message.group_sequence > 0 else None
        elif active.expected_groups is None or message.group_sequence != active.next_sequence:
            active.sequence_error = True
        else:
            active.next_sequence = message.group_sequence - 1 if message.group_sequence is not None and message.group_sequence > 0 else None
        active.continuations.append(message)
        if active.sequence_error:
            active.status = "sequence_conflict_unverified"
        elif message.group_sequence == 0 and active.expected_groups == len(active.continuations) + 1:
            active.status = "structurally_complete_unverified"

    def _append_candidate(self, candidate: MessageCandidate) -> None:
        self._candidates.append(candidate)
        if len(self._candidates) > self._max_candidates:
            expired = self._candidates.pop(0)
            key = (expired.pi, expired.continuity_index)
            if self._active.get(key) is expired:
                del self._active[key]

    def summary(self) -> dict:
        self.expire()
        return {
            "candidate_count": len(self._candidates),
            "orphan_continuations": self.orphan_continuations,
            "expired_candidates": self.expired_candidates,
            "complete_verified": 0,
            "structurally_complete_unverified": sum(
                item.status == "structurally_complete_unverified" for item in self._candidates
            ),
            "candidates": [item.as_dict() for item in self._candidates],
            "warning": "Candidates are not confirmed incidents. Sequence termination, event tables and encrypted locations remain unresolved.",
        }
