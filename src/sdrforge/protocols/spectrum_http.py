# SPDX-License-Identifier: MIT
"""!
@brief Localhost HTTP spectrum endpoint for UI adapters.

Read-only latest-frame JSON snapshots. HTTP threads never touch IQ or hardware.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from sdrforge.controllers.spectrum_publisher import SpectrumPublisher
from sdrforge.models.spectrum_frame import SpectrumFrame


def frame_to_dict(frame: SpectrumFrame) -> dict[str, Any]:
    """!
    @brief Versioned wire format for clients outside libSDRForge.

    @param frame The ``frame`` value.
    @return The operation result.
    """
    return {
        "version": 1,
        "center_frequency_hz": frame.center_frequency_hz,
        "sample_rate_hz": frame.sample_rate_hz,
        "timestamp_ns": frame.timestamp_ns,
        "fft_size": frame.fft_size,
        "bin_width_hz": frame.bin_width_hz,
        "power_unit": "relative_dBFS",
        "power_dbfs": list(frame.power_dbfs),
    }


class SpectrumHttpServer(ThreadingHTTPServer):
    """!
    @brief Read shared publisher snapshots without consuming subscriber frames.
    """

    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self, publisher: SpectrumPublisher, host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param publisher The ``publisher`` value.
        @param host The ``host`` value.
        @param port The ``port`` value.
        """
        self._publisher = publisher
        super().__init__((host, port), SpectrumHttpHandler)


class SpectrumHttpHandler(BaseHTTPRequestHandler):
    """!
    @brief Provide spectrum http handler behavior.
    """
    server: SpectrumHttpServer

    def do_GET(self) -> None:
        """!
        @brief Handle an HTTP GET request.

        @param self The current instance.
        """
        if self.path != "/v1/spectrum/latest":
            self.send_error(404)
            return
        frame = self.server._publisher.latest_frame()
        if frame is None:
            self.send_response(204)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        body = json.dumps(frame_to_dict(frame), separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """!
        @brief Avoid logging every spectrum refresh.

        @param self The current instance.
        @param format The ``format`` value.
        @param args The ``args`` value.
        """
