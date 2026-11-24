"""Chunk boundary coverage for ADS-B IQ streaming."""

import numpy as np
import pytest

from sdrforge.adsb.iq_stream import StreamingAdsbDemodulator
from sdrforge.adsb.iq_synthetic import synthesize_iq
from sdrforge.adsb.receiver_cli import SYNTHETIC_FRAMES


@pytest.mark.parametrize("rate", [2e6, 2.4e6])
@pytest.mark.parametrize("chunk_size", [1, 7, 59, 240, 4096])
def test_streaming_chunk_boundaries(rate, chunk_size):
    frames = tuple(bytes.fromhex(x) for x in SYNTHETIC_FRAMES)
    iq = synthesize_iq(frames, rate)
    receiver = StreamingAdsbDemodulator(rate)
    received = []
    for start in range(0, len(iq), chunk_size):
        received.extend(receiver.feed(iq[start : start + chunk_size]))
        assert receiver.buffered_samples < int(np.ceil(120 * rate / 1e6))
    assert tuple(received) == frames


def test_empty_feed_and_reset():
    receiver = StreamingAdsbDemodulator(2e6)
    assert receiver.feed(np.empty(0, dtype=np.complex64)) == ()
    receiver.feed(np.ones(10, dtype=np.complex64))
    assert receiver.buffered_samples == 10
    receiver.reset()
    assert receiver.buffered_samples == 0


def test_bad_rate_and_shape():
    with pytest.raises(ValueError):
        StreamingAdsbDemodulator(1e6)
    with pytest.raises(ValueError):
        StreamingAdsbDemodulator(2e6).feed(np.zeros((2, 2)))
