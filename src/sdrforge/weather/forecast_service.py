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

    def publish(self, event: Mapping[str, object]) -> dict[str, object]:
        """Serialize record and publication order across receiver callbacks."""
        with self._lock:
            record = self.history.record(event)
            if self._submit is not None:
                self._submit("noaa.forecast", deepcopy(record))
            return record
