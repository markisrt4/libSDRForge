# SPDX-License-Identifier: MIT
"""Optional ZeroMQ PUB transport for binary spectrum frames."""
from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import numpy as np

from sdrforge.models.spectrum_frame import SpectrumFrame

if TYPE_CHECKING:
    import zmq

TOPIC = b"sdrforge.v1.spectrum"
# Magic, version, center Hz, sample rate Hz, timestamp ns, number of bins
_HEADER = struct.Struct("<4sBQQQI")


def encode_spectrum(frame: SpectrumFrame) -> bytes:
    """Encode a versioned little-endian float32 spectrum frame."""
    if frame.fft_size < 2 or frame.sample_rate_hz <= 0:
        raise ValueError("invalid spectrum frame")
    bins = np.asarray(frame.power_dbfs, dtype="<f4")
    header = _HEADER.pack(
        b"SDF1", 1, frame.center_frequency_hz,
        frame.sample_rate_hz, frame.timestamp_ns, frame.fft_size,
    )
    return header + bins.tobytes()


def decode_spectrum(payload: bytes) -> SpectrumFrame:
    """Decode a complete frame without retaining the network buffer."""
    if len(payload) < _HEADER.size:
        raise ValueError("truncated spectrum header")
    magic, version, center, rate, timestamp, count = _HEADER.unpack_from(payload)
    if magic != b"SDF1" or version != 1 or rate <= 0 or count < 2:
        raise ValueError("unsupported spectrum frame")
    if len(payload) != _HEADER.size + count * 4:
        raise ValueError("incorrect spectrum payload size")
    bins = np.frombuffer(payload, dtype="<f4", offset=_HEADER.size, count=count)
    return SpectrumFrame(
        center_frequency_hz=center, sample_rate_hz=rate,
        timestamp_ns=timestamp, power_dbfs=tuple(float(v) for v in bins),
    )


class SpectrumZmqPublisher:
    """PUB adapter; caller owns its thread and invokes send_frame there."""

    def __init__(self, endpoint: str, *, hwm: int = 2) -> None:
        if hwm < 1:
            raise ValueError("hwm must be positive")
        try:
            import zmq
        except ImportError as exc:
            raise RuntimeError("install pyzmq to enable ZeroMQ spectrum") from exc
        self._zmq = zmq
        self._socket: zmq.Socket[bytes] = zmq.Context.instance().socket(zmq.PUB)
        self._socket.setsockopt(zmq.SNDHWM, hwm)
        self._socket.setsockopt(zmq.LINGER, 0)
        try:
            self._socket.bind(endpoint)
        except BaseException:
            self._socket.close()
            raise

    def send_frame(self, frame: SpectrumFrame) -> bool:
        """Nonblocking send; return False when the transport drops a frame."""
        try:
            self._socket.send_multipart([TOPIC, encode_spectrum(frame)], flags=self._zmq.NOBLOCK)
            return True
        except self._zmq.Again:
            return False

    def close(self) -> None:
        self._socket.close()
