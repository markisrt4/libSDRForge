# SPDX-License-Identifier: MIT
"""Binary spectrum wire format tests, without ZeroMQ or hardware."""
import numpy as np
import pytest

from sdrforge.models.spectrum_frame import spectrum_from_iq
from sdrforge.protocols.spectrum_zmq import decode_spectrum, encode_spectrum


def test_binary_spectrum_roundtrip() -> None:
    iq = np.exp(2j * np.pi * 9 * np.arange(128) / 128)
    frame = spectrum_from_iq(iq, center_frequency_hz=104_300_000,
                             sample_rate_hz=2_400_000, timestamp_ns=123456)
    payload = encode_spectrum(frame)
    assert len(payload) == 33 + 128 * 4
    restored = decode_spectrum(payload)
    assert restored.center_frequency_hz == frame.center_frequency_hz
    assert restored.sample_rate_hz == frame.sample_rate_hz
    assert restored.timestamp_ns == frame.timestamp_ns
    assert restored.power_dbfs == pytest.approx(frame.power_dbfs, abs=0.0001)


def test_binary_spectrum_rejects_corrupt_payload() -> None:
    with pytest.raises(ValueError):
        decode_spectrum(b"broken")
    iq = np.ones(32, dtype=np.complex64)
    frame = spectrum_from_iq(iq, center_frequency_hz=100_000_000,
                             sample_rate_hz=1_000_000, timestamp_ns=1)
    payload = encode_spectrum(frame)
    with pytest.raises(ValueError, match="payload size"):
        decode_spectrum(payload[:-1])
