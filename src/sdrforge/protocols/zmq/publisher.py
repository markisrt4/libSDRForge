# SPDX-License-Identifier: MIT
"""Nonblocking ZeroMQ PUB transport for SDR telemetry.

The caller owns pacing and calls publish() from the DSP/telemetry producer.
A saturated subscriber must never stall the DSP thread.
"""
from __future__ import annotations

import json
from typing import Any


class ZmqTelemetryPublisher:
    """Publish versioned JSON envelopes with topic-based subscriptions."""

    def __init__(
        self, endpoint: str = "tcp://127.0.0.1:5571",
        *,
        context: Any = None,
        socket: Any = None,
    ) -> None:
        if socket is None:
            try:
                import zmq
            except ImportError as exc:
                raise RuntimeError(
                    "ZeroMQ streaming requires pyzmq; install libsdrforge[zmq]"
                ) from exc
            self._zmq = zmq
            self._context = context if context is not None else zmq.Context.instance()
            socket = self._context.socket(zmq.PUB)
            socket.setsockopt(zmq.SNDHWM, 8)
            socket.setsockopt(zmq.LINGER, 0)
            socket.bind(endpoint)
        else:
            self._zmq = None
            self._context = context
        self._socket = socket
        self.dropped_messages = 0

    def publish(self, topic: str, payload: dict[str, Any]) -> bool:
        """Return False when the output queue is full; never block."""
        if not topic or any(ch.isspace() for ch in topic):
            raise ValueError("topic must be nonempty and contain no whitespace")
        envelope = {"schema_version": 1, "payload": payload}
        message = topic.encode("ascii") + b" " + json.dumps(
            envelope, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
        try:
            if self._zmq is None:
                self._socket.send(message, flags=1)
            else:
                self._socket.send(message, flags=self._zmq.NOBLOCK)
        except BlockingIOError:
            self.dropped_messages += 1
            return False
        except Exception as exc:  # noqa: BLE001 - pyzmq Again is optional at runtime
            if self._zmq is not None and isinstance(exc, self._zmq.Again):
                self.dropped_messages += 1
                return False
            raise
        return True

    def close(self) -> None:
        self._socket.close()
