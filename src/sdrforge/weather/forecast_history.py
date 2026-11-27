# SPDX-License-Identifier: MIT
"""Authoritative in-process history of completed NOAA RF forecasts."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from copy import deepcopy
from threading import Lock
from time import time
from uuid import uuid4


class NoaaForecastHistory:
    """Retain bounded broadcast history independently of telemetry consumers."""

    def __init__(
        self, *, capacity: int = 128, clock: Callable[[], float] = time
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._clock = clock
        self._lock = Lock()
        self._records: deque[dict[str, object]] = deque(maxlen=capacity)
        self._publisher_id = uuid4().hex
        self._sequence = 0

    def record(self, event: Mapping[str, object]) -> dict[str, object]:
        """Record a completed forecast before publishing it to consumers."""
        if event.get("event") != "noaa_forecast_completed":
            raise ValueError("expected noaa_forecast_completed")
        completed = event.get("completed_forecast")
        if not isinstance(completed, dict) or not isinstance(
            completed.get("forecast"), dict
        ):
            raise TypeError("completed forecast is required")
        with self._lock:
            self._sequence += 1
            record = deepcopy(dict(event))
            record["publisher_id"] = self._publisher_id
            record["publisher_sequence"] = self._sequence
            record["received_at"] = self._clock()
            self._records.append(record)
            return deepcopy(record)

    def latest(self) -> dict[str, object] | None:
        """Return the latest record without exposing mutable internal state."""
        with self._lock:
            return deepcopy(self._records[-1]) if self._records else None

    def history(self) -> list[dict[str, object]]:
        """Return retained records in reception order."""
        with self._lock:
            return deepcopy(list(self._records))

    def status(self) -> dict[str, object]:
        """Describe retained data, without claiming the receiver is running."""
        with self._lock:
            latest = self._records[-1] if self._records else None
            received_at = latest["received_at"] if latest is not None else None
            age = (
                max(0.0, self._clock() - received_at)
                if isinstance(received_at, (int, float))
                else None
            )
            return {
                "schema_version": 1,
                "publisher_id": self._publisher_id,
                "record_count": len(self._records),
                "received_at": received_at,
                "reception_age_seconds": age,
                "receiver_running": None,
            }
