"""HTTP contract tests for optional NOAA history."""

import json
from threading import Thread
from typing import cast
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from sdrforge.interfaces.receiver_control_if import ReceiverControlIf
from sdrforge.protocols.rest.server import RestControlServer
from sdrforge.weather.forecast_history import NoaaForecastHistory


@pytest.mark.parametrize("enabled", [False, True])
def test_noaa_rest_contract(enabled):
    now = [100.0]
    history = NoaaForecastHistory(clock=lambda: now[0])
    server = RestControlServer(
        cast(ReceiverControlIf, object()),
        port=0,
        noaa_history=history if enabled else None,
    )
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}/v1/weather/noaa"

    def get(path):
        with urlopen(f"{base}/{path}", timeout=3) as response:
            return json.load(response)

    try:
        if not enabled:
            for path in ("latest", "history", "status"):
                with pytest.raises(HTTPError) as error:
                    get(path)
                assert error.value.code == 404
                error.value.close()
            return

        assert get("latest") == {"schema_version": 1, "payload": None}
        assert get("history")["records"] == []
        assert get("status")["reception_age_seconds"] is None
        record = history.record(
            {
                "event": "noaa_forecast_completed",
                "completed_forecast": {"forecast": {"period": "tonight"}},
            }
        )
        now[0] = 115.0
        assert get("latest")["payload"] == record
        assert get("history")["records"] == [record]
        status = get("status")
        assert status["record_count"] == 1
        assert status["reception_age_seconds"] == 15.0
        assert status["receiver_running"] is None
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
