"""Runtime-owned NOAA forecast publication independent of receiver ownership."""

from collections.abc import Callable, Mapping
from copy import deepcopy
from threading import Lock

from sdrforge.weather.forecast_history import NoaaForecastHistory


class NoaaForecastService:
    """Record forecasts before submitting best-effort telemetry."""

    def __init__(
        self,
        submit: Callable[[str, dict[str, object]], bool] | None = None,
        *,
        history: NoaaForecastHistory | None = None,
    ) -> None:
        self.history = history if history is not None else NoaaForecastHistory()
        self._submit = submit
        self._lock = Lock()
        self._generation = 0
        self._active_generation: int | None = None

    def publish(self, event: Mapping[str, object]) -> dict[str, object]:
        """Serialize record and publication order across receiver callbacks."""
        with self._lock:
            return self._publish_locked(event)

    def begin_session(self) -> int:
        """Invalidate previous callbacks and return a new reception generation."""
        with self._lock:
            self._generation += 1
            self._active_generation = self._generation
            return self._generation

    def end_session(self, generation: int) -> None:
        """Invalidate callbacks only for the specified reception generation."""
        with self._lock:
            if self._active_generation == generation:
                self._active_generation = None

    def publish_session(
        self, generation: int, event: Mapping[str, object]
    ) -> dict[str, object] | None:
        """Discard results from inactive reception generations."""
        with self._lock:
            if self._active_generation != generation:
                return None
            return self._publish_locked(event)

    def _publish_locked(self, event: Mapping[str, object]) -> dict[str, object]:
        record = self.history.record(event)
        if self._submit is not None:
            self._submit("noaa.forecast", deepcopy(record))
        return record
