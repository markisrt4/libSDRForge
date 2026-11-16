# SPDX-License-Identifier: MIT
"""REST receiver control adapter sharing the same receiver as RigCTL."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any

from sdrforge.controllers.receiver_service import ReceiverService


class ReceiverHttpServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self, receiver: ReceiverService, host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self.receiver = receiver
        super().__init__((host, port), ReceiverHttpHandler)


class ReceiverHttpHandler(BaseHTTPRequestHandler):
    server: ReceiverHttpServer

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _status(self) -> dict[str, Any]:
        receiver = self.server.receiver
        mode, bandwidth = receiver.get_mode()
        return {
            "version": 1,
            "state": receiver.state.value,
            "last_error": receiver.last_error,
            "frequency_hz": receiver.get_frequency(),
            "mode": mode,
            "bandwidth_hz": bandwidth,
        }

    def do_GET(self) -> None:
        if self.path != "/v1/receiver":
            self._send_json(404, {"error": "not_found"})
            return
        try:
            self._send_json(200, self._status())
        except (RuntimeError, OSError) as exc:
            self._send_json(503, {"error": str(exc)})

    def do_POST(self) -> None:
        operations = {
            "/v1/receiver/start": self.server.receiver.start,
            "/v1/receiver/stop": self.server.receiver.stop,
            "/v1/receiver/restart": self.server.receiver.restart,
        }
        action = operations.get(self.path)
        if action is None:
            self._send_json(404, {"error": "not_found"})
            return
        if self.headers.get("Content-Length", "0") not in {"", "0"}:
            self._send_json(400, {"error": "unexpected_body"})
            return
        try:
            action()
            self._send_json(200, self._status())
        except (RuntimeError, OSError) as exc:
            self._send_json(503, {"error": str(exc)})

    def do_PUT(self) -> None:
        if self.path != "/v1/receiver/tuning":
            self._send_json(404, {"error": "not_found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError("invalid body length")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("expected JSON object")
            frequency = data.get("frequency_hz")
            mode = data.get("mode")
            bandwidth = data.get("bandwidth_hz")
            if frequency is None and mode is None and bandwidth is None:
                raise ValueError("no tuning fields")
            if frequency is not None and (type(frequency) is not int or frequency <= 0):
                raise ValueError("invalid frequency_hz")
            if (mode is None) != (bandwidth is None):
                raise ValueError("mode and bandwidth_hz must be provided together")
            if mode is not None and (
                not isinstance(mode, str) or mode.upper() not in {"FM", "NFM", "WFM", "AM"}
                or type(bandwidth) is not int or bandwidth < 0
            ):
                raise ValueError("invalid mode or bandwidth_hz")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": str(exc)})
            return
        try:
            receiver = self.server.receiver
            if frequency is not None:
                receiver.set_frequency(frequency)
            if mode is not None:
                receiver.set_mode(mode.upper(), bandwidth)
            self._send_json(200, self._status())
        except (RuntimeError, OSError) as exc:
            self._send_json(503, {"error": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        """Suppress routine polling logs."""
