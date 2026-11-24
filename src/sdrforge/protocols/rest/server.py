# SPDX-License-Identifier: MIT
"""!
@brief Localhost REST control for a ReceiverControlIf-compatible manager.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from sdrforge.interfaces.receiver_control_if import ReceiverControlIf
from sdrforge.protocols.rest.radio_api import RadioApi


class RestControlServer(ThreadingHTTPServer):
    """!
    @brief Inject a receiver or ReceiverManager; no SDR hardware is required.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        receiver: ReceiverControlIf,
        host: str = "127.0.0.1",
        port: int = 5570,
        shutdown_callback: Callable[[], None] | None = None,
        capture_control: Any | None = None,
        source_type: str | None = None,
        radio_api: RadioApi | None = None,
    ) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param receiver The ``receiver`` value.
        @param host The ``host`` value.
        @param port The ``port`` value.
        @param shutdown_callback The ``shutdown_callback`` value.
        @param capture_control Optional IQ capture service.
        @param source_type Actual IQ source selected at server startup.
        @param radio_api Optional radio catalog and preset request dispatcher.
        """
        self.receiver = receiver
        self.shutdown_callback = shutdown_callback
        self.capture_control = capture_control
        self.source_type = source_type
        self.radio_api = radio_api
        super().__init__((host, port), RestControlHandler)


class RestControlHandler(BaseHTTPRequestHandler):
    """!
    @brief Provide rest control handler behavior.
    """

    server: RestControlServer

    def log_message(self, format: str, *args: object) -> None:
        """!
        @brief Avoid noisy per-request console output.

        @param self The current instance.
        @param format The ``format`` value.
        @param args The ``args`` value.
        """

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            # A client timed out or closed before the response was delivered.
            pass

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 4096:
            raise ValueError("request body must be 1 to 4096 bytes")
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise TypeError("JSON object required")
        return body

    def do_GET(self) -> None:
        """!
        @brief Handle an HTTP GET request.

        @param self The current instance.
        """
        receiver = self.server.receiver
        if self.path.startswith("/v1/radio/"):
            api = self.server.radio_api
            status, payload = (
                api.dispatch("GET", self.path)
                if api is not None
                else (404, {"error": "radio_api_not_configured"})
            )
            self._respond(status, payload)
            return
        try:
            if self.path == "/v1/health":
                self._respond(200, {"status": "ok"})
            elif self.path == "/v1/rf/config":
                self._respond(200, receiver.get_rf_configuration())
            elif self.path == "/v1/capture/iq":
                capture = self.server.capture_control
                if capture is None:
                    self._respond(404, {"error": "capture_not_supported"})
                else:
                    self._respond(200, capture.iq_capture_status())
            elif self.path == "/v1/audio":
                getter = getattr(receiver, "get_audio_diagnostics", None)
                diagnostics = getter() if callable(getter) else {}
                self._respond(200, {**diagnostics, "muted": receiver.get_muted()})
            elif self.path == "/v1/receiver":
                mode, bandwidth = receiver.get_mode()
                rds_status = getattr(receiver, "get_rds_status", None)
                self._respond(
                    200,
                    {
                        "frequency_hz": receiver.get_frequency(),
                        "source_type": self.server.source_type,
                        "running": getattr(receiver, "running", False),
                        "starting": getattr(receiver, "starting", False),
                        "startup_error": getattr(receiver, "startup_error", None),
                        "startup_elapsed_ms": getattr(
                            receiver, "startup_elapsed_ms", None
                        ),
                        "startup_duration_ms": getattr(
                            receiver, "startup_duration_ms", None
                        ),
                        "mode": mode,
                        "bandwidth_hz": bandwidth,
                        "signal_strength": receiver.get_signal_strength(),
                        "snr": receiver.get_snr(),
                        "rds": (
                            rds_status() if callable(rds_status) else receiver.get_rds()
                        ),
                    },
                )
            else:
                self._respond(404, {"error": "not_found"})
        except (OSError, RuntimeError, ValueError) as exc:
            self._respond(503, {"error": str(exc)})

    def _radio_mutation(self, method: str) -> None:
        api = self.server.radio_api
        if api is None:
            self._respond(404, {"error": "radio_api_not_configured"})
            return
        try:
            body = self._read_json()
            status, payload = api.dispatch(method, self.path, body)
            self._respond(status, payload)
        except (ValueError, TypeError) as exc:
            self._respond(400, {"error": str(exc)})
        except (OSError, RuntimeError) as exc:
            self._respond(503, {"error": str(exc)})

    def do_PATCH(self) -> None:
        """!
        @brief Handle an HTTP PATCH request.
        @param self The current instance.
        """
        if self.path.startswith("/v1/radio/"):
            self._radio_mutation("PATCH")
        else:
            self._respond(404, {"error": "not_found"})

    def do_DELETE(self) -> None:
        """!
        @brief Handle an HTTP DELETE request.
        @param self The current instance.
        """
        if self.path.startswith("/v1/radio/"):
            self._radio_mutation("DELETE")
        else:
            self._respond(404, {"error": "not_found"})

    def do_POST(self) -> None:
        """!
        @brief Handle an HTTP POST request.

        @param self The current instance.
        """
        if self.path.startswith("/v1/radio/"):
            self._radio_mutation("POST")
            return
        if self.path == "/v1/capture/iq/stop":
            capture = self.server.capture_control
            if capture is None:
                self._respond(404, {"error": "capture_not_supported"})
            else:
                self._respond(200, capture.cancel_iq_capture())
            return
        if self.path == "/v1/capture/iq":
            capture = self.server.capture_control
            if capture is None:
                self._respond(404, {"error": "capture_not_supported"})
                return
            try:
                body = self._read_json()
                if body.get("auto_start_receiver", False) is True:
                    result = capture.start_automated_iq_capture(
                        body.get("duration_seconds", 30),
                        body.get("filename", "rds_capture.iq"),
                    )
                elif body.get("auto_start_receiver", False) is not False:
                    raise ValueError("auto_start_receiver must be boolean")
                else:
                    result = capture.start_iq_capture(
                        body.get("duration_seconds", 30),
                        body.get("filename", "rds_capture.iq"),
                    )
                self._respond(202, result)
            except (TypeError, ValueError) as exc:
                self._respond(400, {"error": str(exc)})
            except (OSError, RuntimeError) as exc:
                self._respond(409, {"error": str(exc)})
            return
        if self.path == "/v1/server/shutdown":
            callback = self.server.shutdown_callback
            if callback is None:
                self._respond(404, {"error": "shutdown_not_supported"})
                return
            self._respond(200, {"ok": True, "stopping": True})
            import threading

            threading.Thread(target=callback, daemon=True).start()
            return
        receiver = self.server.receiver
        if self.path not in {
            "/v1/receiver/frequency",
            "/v1/receiver/recenter",
            "/v1/receiver/pan",
            "/v1/rf/config",
            "/v1/receiver/mode",
            "/v1/receiver/start",
            "/v1/receiver/stop",
            "/v1/audio/mute",
            "/v1/audio/unmute",
        }:
            self._respond(404, {"error": "not_found"})
            return
        try:
            if self.path == "/v1/rf/config":
                receiver.set_rf_configuration(self._read_json())
            elif self.path == "/v1/receiver/pan":
                pan = getattr(receiver, "pan_acquisition", None)
                if not callable(pan):
                    raise RuntimeError("acquisition pan is not supported")
                pan(int(self._read_json()["center_hz"]))
                self._respond(202, {"ok": True})
                return
            elif self.path == "/v1/receiver/recenter":
                recenter = getattr(receiver, "recenter", None)
                if not callable(recenter):
                    raise RuntimeError("acquisition recenter is not supported")
                recenter()
                self._respond(202, {"ok": True})
                return
            elif self.path == "/v1/receiver/frequency":
                body = self._read_json()
                hz = body.get("frequency_hz")
                if type(hz) is not int or hz <= 0:
                    raise ValueError("frequency_hz must be a positive integer")
                receiver.set_frequency(hz)
            elif self.path == "/v1/receiver/mode":
                body = self._read_json()
                mode = body.get("mode")
                bandwidth = body.get("bandwidth_hz")
                if not isinstance(mode, str) or mode.upper() not in {
                    "FM",
                    "NFM",
                    "WFM",
                    "AM",
                }:
                    raise ValueError("unsupported mode")
                if type(bandwidth) is not int or bandwidth < 0:
                    raise ValueError("bandwidth_hz must be a nonnegative integer")
                receiver.set_mode(mode.upper(), bandwidth)
            elif self.path in ("/v1/audio/mute", "/v1/audio/unmute"):
                receiver.set_muted(self.path.endswith("/mute"))
            elif self.path == "/v1/receiver/start":
                if hasattr(receiver, "start_async"):
                    receiver.start_async()
                    self._respond(202, {"ok": True, "starting": True})
                    return
                receiver.start()
            else:
                receiver.stop()
        except (TypeError, ValueError) as exc:
            self._respond(400, {"error": str(exc)})
            return
        except (OSError, RuntimeError) as exc:
            self._respond(503, {"error": str(exc)})
            return
        self._respond(200, {"ok": True})
