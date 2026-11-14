# SPDX-License-Identifier: MIT
"""Bounded, asynchronous telemetry delivery independent of DSP processing."""
from __future__ import annotations

from collections.abc import Callable
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Any, Protocol

from sdrforge.protocols.zmq.publisher import ZmqTelemetryPublisher
from sdrforge.telemetry.snapshots import receiver_snapshot, spectrum_snapshot


class PublisherIf(Protocol):
    def publish(self, topic: str, payload: dict[str, Any]) -> bool: ...
    def close(self) -> None: ...


class TelemetryStream:
    """Queue immutable snapshots; the worker owns the ZeroMQ socket.

    A full queue drops new telemetry rather than blocking the DSP producer.
    The producer must call submit_* with already available receiver data.
    """

    def __init__(
        self,
        *,
        endpoint: str = "tcp://127.0.0.1:5571",
        capacity: int = 16,
        publisher_factory: Callable[[], PublisherIf] | None = None,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._queue: Queue[tuple[str, dict[str, Any]]] = Queue(maxsize=capacity)
        self._factory = publisher_factory or (lambda: ZmqTelemetryPublisher(endpoint))
        self._thread: Thread | None = None
        self._stop = Event()
        self._ready = Event()
        self._error: BaseException | None = None
        self.dropped_messages = 0
        self.published_messages = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("telemetry stream cannot be restarted")
        self._stop.clear()
        self._ready.clear()
        self._thread = Thread(target=self._run, name="sdrforge-telemetry", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        if self._error is not None:
            raise RuntimeError("telemetry publisher failed to start") from self._error
        if not self._ready.is_set():
            raise RuntimeError("telemetry publisher startup timed out")

    def _run(self) -> None:
        publisher: PublisherIf | None = None
        try:
            publisher = self._factory()
            self._ready.set()
            while not self._stop.is_set() or not self._queue.empty():
                try:
                    topic, payload = self._queue.get(timeout=0.05)
                except Empty:
                    continue
                try:
                    if publisher.publish(topic, payload):
                        self.published_messages += 1
                    else:
                        self.dropped_messages += 1
                finally:
                    self._queue.task_done()
        except Exception as exc:
            self._error = exc
        finally:
            self._ready.set()
            if publisher is not None:
                publisher.close()

    def submit(self, topic: str, payload: dict[str, Any]) -> bool:
        if not self.running:
            return False
        try:
            self._queue.put_nowait((topic, payload))
        except Full:
            self.dropped_messages += 1
            return False
        return True

    def submit_spectrum(
        self,
        power_db: Any,
        *,
        center_frequency_hz: int,
        sample_rate_hz: int,
        timestamp_ns: int | None = None,
    ) -> bool:
        return self.submit("spectrum", spectrum_snapshot(
            power_db,
            center_frequency_hz=center_frequency_hz,
            sample_rate_hz=sample_rate_hz,
            timestamp_ns=timestamp_ns,
        ))

    def submit_receiver(self, receiver: Any, *, timestamp_ns: int | None = None) -> bool:
        return self.submit("receiver", receiver_snapshot(receiver, timestamp_ns=timestamp_ns))

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                raise RuntimeError("telemetry worker did not stop")
        if self._error is not None:
            raise RuntimeError("telemetry worker failed") from self._error
