# SPDX-License-Identifier: MIT
"""Run ZeroMQ spectrum publication outside the IQ acquisition thread."""
from __future__ import annotations

from threading import Event, Thread

from sdrforge.controllers.spectrum_publisher import SpectrumPublisher, SpectrumSubscription
from sdrforge.protocols.spectrum_zmq import SpectrumZmqPublisher


class SpectrumZmqBridge:
    """A single owner thread for the ZeroMQ PUB socket.

    The receiver publishes IQ to SpectrumPublisher; this bridge reads a
    bounded subscription and forwards only the newest spectrum frame.
    """

    def __init__(
        self, publisher: SpectrumPublisher, endpoint: str,
        *, hwm: int = 2, poll_seconds: float = 0.02,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        self._publisher = publisher
        self._endpoint = endpoint
        self._hwm = hwm
        self._poll_seconds = poll_seconds
        self._stop = Event()
        self._thread: Thread | None = None
        self._subscription: SpectrumSubscription | None = None
        self._transport: SpectrumZmqPublisher | None = None
        self._ready = Event()
        self._startup_error: Exception | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("spectrum bridge already started")
        self._subscription = self._publisher.subscribe(max_frames=1)
        self._stop.clear()
        self._ready.clear()
        self._startup_error = None
        self._thread = Thread(target=self._run, name="sdrforge-spectrum-zmq", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            self.stop()
            raise RuntimeError("spectrum bridge startup timed out")
        if self._startup_error is not None:
            error = self._startup_error
            self.stop()
            raise RuntimeError("spectrum bridge startup failed") from error

    def _run(self) -> None:
        # Create, use, and close the PUB socket on the same thread.
        transport: SpectrumZmqPublisher | None = None
        try:
            try:
                transport = SpectrumZmqPublisher(self._endpoint, hwm=self._hwm)
                self._transport = transport
            except Exception as exc:
                self._startup_error = exc
                return
            finally:
                self._ready.set()
            while not self._stop.wait(self._poll_seconds):
                subscription = self._subscription
                if subscription is None:
                    break
                frame = subscription.poll_latest()
                if frame is not None:
                    transport.send_frame(frame)
        finally:
            if transport is not None:
                transport.close()
            self._ready.set()

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._stop.set()
        thread.join()
        subscription = self._subscription
        if subscription is not None:
            self._publisher.unsubscribe(subscription)
        self._subscription = None
        self._transport = None
        self._thread = None
