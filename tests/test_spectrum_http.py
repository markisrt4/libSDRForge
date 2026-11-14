# SPDX-License-Identifier: MIT
"""HTTP spectrum contract tested without SDR hardware."""
from __future__ import annotations

import json
from threading import Thread
from urllib.request import urlopen

import numpy as np

from sdrforge.controllers.spectrum_publisher import SpectrumPublisher
from sdrforge.protocols.spectrum_http import SpectrumHttpServer


def test_spectrum_http_latest_and_empty() -> None:
    publisher = SpectrumPublisher(fft_size=128, max_fps=15)
    server = SpectrumHttpServer(publisher)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/v1/spectrum/latest", timeout=2) as response:
            assert response.status == 204
    finally:
        server.shutdown()
        server.close()
        thread.join(timeout=2)


def test_spectrum_http_frame_contract() -> None:
    publisher = SpectrumPublisher(fft_size=128)
    server = SpectrumHttpServer(publisher)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        iq = np.exp(2j * np.pi * 7 * np.arange(128) / 128)
        publisher.publish_iq(iq, center_frequency_hz=104_300_000,
                             sample_rate_hz=1_280_000, timestamp_ns=123)
        with urlopen(base + "/v1/spectrum/latest", timeout=2) as response:
            assert response.status == 200
            payload = json.load(response)
        assert payload["version"] == 1
        assert payload["center_frequency_hz"] == 104_300_000
        assert payload["fft_size"] == 128
        assert payload["power_unit"] == "relative_dBFS"
        assert len(payload["power_dbfs"]) == 128
        with urlopen(base + "/v1/spectrum/latest", timeout=2) as response:
            assert response.status == 204
    finally:
        server.shutdown()
        server.close()
        thread.join(timeout=2)
