# SPDX-License-Identifier: MIT
"""Localhost REST control for a ReceiverControlIf-compatible manager."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from sdrforge.interfaces.receiver_control import ReceiverControlIf


class RestControlServer(ThreadingHTTPServer):
    """Inject a receiver or ReceiverManager; no SDR hardware is required."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, receiver: ReceiverControlIf, host: str = "127.0.0.1", port: int = 5570
    ) -> None:
        self.receiver = receiver
        super().__init__((host, port), RestControlHandler)


class RestControlHandler(BaseHTTPRequestHandler):
    server: RestControlServer

    def log_message(self, format: str, *args: object) -> None:
        """Avoid noisy per-request console output."""

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 4096:
            raise ValueError("request body must be 1 to 4096 bytes")
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise TypeError("JSON object required")
        return body

    def do_GET(self) -> None:
        receiver = self.server.receiver
        try:
            if self.path == "/v1/health":
                self._respond(200, {"status": "ok"})
            elif self.path == "/v1/receiver":
                mode, bandwidth = receiver.get_mode()
                self._respond(200, {
                    "frequency_hz": receiver.get_frequency(),
                    "mode": mode,
                    "bandwidth_hz": bandwidth,
                    "signal_strength": receiver.get_signal_strength(),
                    "snr": receiver.get_snr(),
                    "rds": receiver.get_rds(),
                })
            else:
                self._respond(404, {"error": "not_found"})
        except (OSError, RuntimeError, ValueError) as exc:
            self._respond(503, {"error": str(exc)})

    def do_POST(self) -> None:
        receiver = self.server.receiver
        if self.path not in {
            "/v1/receiver/frequency",
            "/v1/receiver/mode",
            "/v1/receiver/start",
            "/v1/receiver/stop",
        }:
            self._respond(404, {"error": "not_found"})
            return
        try:
            if self.path == "/v1/receiver/frequency":
                body = self._read_json()
                hz = body.get("frequency_hz")
                if type(hz) is not int or hz <= 0:
                    raise ValueError("frequency_hz must be a positive integer")
                receiver.set_frequency(hz)
            elif self.path == "/v1/receiver/mode":
                body = self._read_json()
                mode = body.get("mode")
                bandwidth = body.get("bandwidth_hz")
                if not isinstance(mode, str) or mode.upper() not in {"FM", "NFM", "WFM", "AM"}:
                    raise ValueError("unsupported mode")
                if type(bandwidth) is not int or bandwidth < 0:
                    raise ValueError("bandwidth_hz must be a nonnegative integer")
                receiver.set_mode(mode.upper(), bandwidth)
            elif self.path == "/v1/receiver/start":
                receiver.start()
            else:
                receiver.stop()
        except ValueError as exc:
            self._respond(400, {"error": str(exc)})
            return
        except (OSError, RuntimeError) as exc:
            self._respond(503, {"error": str(exc)})
            return
        self._respond(200, {"ok": True})
