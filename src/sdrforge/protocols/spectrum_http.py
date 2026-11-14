# SPDX-License-Identifier: MIT
"""Localhost HTTP spectrum endpoint for UI adapters.

One latest-frame JSON response per request. The HTTP thread never touches IQ
or hardware, and the publisher drops stale frames for slow consumers.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any

from sdrforge.controllers.spectrum_publisher import SpectrumPublisher, SpectrumSubscription
from sdrforge.models.spectrum_frame import SpectrumFrame


def frame_to_dict(frame: SpectrumFrame) -> dict[str, Any]:
    """Versioned wire format for clients outside libSDRForge."""
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
    """A dedicated latest-frame subscription owned by this server."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self, publisher: SpectrumPublisher, host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self._publisher = publisher
        self._subscription: SpectrumSubscription = publisher.subscribe(max_frames=1)
        try:
            super().__init__((host, port), SpectrumHttpHandler)
        except BaseException:
            publisher.unsubscribe(self._subscription)
            raise

    def close(self) -> None:
        """Release the subscription and the listening socket."""
        self._publisher.unsubscribe(self._subscription)
        self.server_close()


class SpectrumHttpHandler(BaseHTTPRequestHandler):
    server: SpectrumHttpServer

    def do_GET(self) -> None:
        if self.path != "/v1/spectrum/latest":
            self.send_error(404)
            return
        frame = self.server._subscription.poll_latest()
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
        """Avoid logging every spectrum refresh."""
