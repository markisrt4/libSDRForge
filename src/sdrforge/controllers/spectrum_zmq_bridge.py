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

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("spectrum bridge already started")
        transport = SpectrumZmqPublisher(self._endpoint, hwm=self._hwm)
        subscription = self._publisher.subscribe(max_frames=1)
        self._transport = transport
        self._subscription = subscription
        self._stop.clear()
        self._thread = Thread(target=self._run, name="sdrforge-spectrum-zmq", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        # Socket creation and use should normally occur on one thread.
        # The transport is created by start() and only sent to here.
        try:
            while not self._stop.wait(self._poll_seconds):
                subscription = self._subscription
                transport = self._transport
                if subscription is None or transport is None:
                    break
                frame = subscription.poll_latest()
                if frame is not None:
                    transport.send_frame(frame)
        finally:
            transport = self._transport
            if transport is not None:
                transport.close()

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
