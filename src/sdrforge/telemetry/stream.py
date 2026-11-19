# SPDX-License-Identifier: MIT
"""!
@brief Bounded, asynchronous telemetry delivery independent of DSP processing.
"""
from __future__ import annotations

from collections.abc import Callable
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Any, Protocol
from uuid import uuid4

from sdrforge.protocols.zmq.publisher import ZmqTelemetryPublisher
from sdrforge.telemetry.snapshots import receiver_snapshot, spectrum_snapshot


class PublisherIf(Protocol):
    """!
    @brief Define the telemetry publisher operations used by the worker.
    """

    def publish(self, topic: str, payload: dict[str, Any]) -> bool:
        """!
        @brief Publish a topic payload and report whether it was accepted.

        @param self The current instance.
        @param topic The telemetry topic.
        @param payload The telemetry payload.
        @return The operation result.
        """
        ...

    def close(self) -> None:
        """!
        @brief Release publisher resources.

        @param self The current instance.
        """
        ...


class TelemetryStream:
    """!
    @brief Queue immutable snapshots; the worker owns the ZeroMQ socket.

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
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param endpoint The ``endpoint`` value.
        @param capacity The ``capacity`` value.
        @param publisher_factory The ``publisher_factory`` value.
        """
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._queue: Queue[tuple[str, dict[str, Any]]] = Queue(maxsize=capacity)
        self._factory = publisher_factory or (lambda: ZmqTelemetryPublisher(endpoint))
        self._thread: Thread | None = None
        self._stop = Event()
        self._ready = Event()
        self._error: BaseException | None = None
        self._stream_id = uuid4().hex
        self._receiver_sequence = 0
        self.dropped_messages = 0
        self.published_messages = 0

    @property
    def running(self) -> bool:
        """!
        @brief Return whether the telemetry worker is running.

        @param self The current instance.
        @return The operation result.
        """
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def start(self) -> None:
        """!
        @brief Start the component.

        @param self The current instance.
        """
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
        except Exception as exc:  # noqa: BLE001 - propagate unexpected worker failures on stop
            self._error = exc
        finally:
            self._ready.set()
            if publisher is not None:
                publisher.close()

    def submit(self, topic: str, payload: dict[str, Any]) -> bool:
        """!
        @brief Submit the component.

        @param self The current instance.
        @param topic The telemetry topic.
        @param payload The telemetry payload.
        @return The operation result.
        """
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
        """!
        @brief Submit spectrum.

        @param self The current instance.
        @param power_db The ``power_db`` value.
        @param center_frequency_hz The ``center_frequency_hz`` value.
        @param sample_rate_hz The sample rate in hertz.
        @param timestamp_ns The ``timestamp_ns`` value.
        @return The operation result.
        """
        return self.submit("spectrum", spectrum_snapshot(
            power_db,
            center_frequency_hz=center_frequency_hz,
            sample_rate_hz=sample_rate_hz,
            timestamp_ns=timestamp_ns,
        ))

    def submit_receiver(
        self, receiver: Any, *, timestamp_ns: int | None = None,
        mode: str = "WFM", bandwidth_hz: int | None = None,
        frequency_hz: int | None = None, running: bool = True,
    ) -> bool:
        """!
        @brief Provide submit receiver behavior.
        @param self The current instance.
        @param receiver The receiver value.
        @param timestamp_ns The timestamp ns value.
        @param mode The mode value.
        @param bandwidth_hz The bandwidth hz value.
        @param frequency_hz The frequency hz value.
        @param running The running value.
        @return The operation result.
        """
        snapshot = receiver_snapshot(
            receiver, timestamp_ns=timestamp_ns, mode=mode,
            bandwidth_hz=bandwidth_hz, frequency_hz=frequency_hz,
            running=running,
        )
        # Sequence numbers belong to this publisher lifetime, not RF time.
        # A new stream_id on restart allows consumers to reset ordering.
        self._receiver_sequence += 1
        snapshot["stream_id"] = self._stream_id
        snapshot["sequence"] = self._receiver_sequence
        return self.submit("receiver", snapshot)

    def stop(self, timeout: float = 5.0) -> None:
        """!
        @brief Stop the component.

        @param self The current instance.
        @param timeout The ``timeout`` value.
        """
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                raise RuntimeError("telemetry worker did not stop")
        if self._error is not None:
            raise RuntimeError("telemetry worker failed") from self._error
