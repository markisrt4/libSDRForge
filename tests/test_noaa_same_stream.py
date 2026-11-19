"""Chunked SAME input tests using deterministic synthetic audio."""
import numpy as np
import pytest

from sdrforge.weather.same_afsk import synthesize_same_audio
from sdrforge.weather.same_stream import StreamingSameCapture

HEADER = b"ZCZC-WXR-RWT-026099+0030-3211200-KDTX/NWS-"


def test_arbitrary_chunks_recover_header():
    audio = synthesize_same_audio(HEADER)
    stream = StreamingSameCapture(24000)
    for offset in range(0, len(audio), 137):
        stream.feed(audio[offset:offset + 137])
    result = stream.flush()
    assert HEADER in result.decoded_bytes
    assert result.messages.alerts == ()
    assert stream.buffered_samples == 0


def test_repeated_header_confirmed_across_chunks():
    audio = synthesize_same_audio(HEADER + b"\x00" + HEADER)
    stream = StreamingSameCapture(24000)
    for offset in range(0, len(audio), 4096):
        stream.feed(audio[offset:offset + 4096])
    result = stream.flush()
    assert len(result.messages.alerts) == 1
    assert result.messages.alerts[0].event == "RWT"


def test_truncation_never_confirms_alert():
    audio = synthesize_same_audio(HEADER + HEADER)
    stream = StreamingSameCapture(24000, max_seconds=0.25)
    stream.feed(audio)
    result = stream.flush()
    assert result.truncated
    assert result.messages.alerts == ()


def test_input_is_copied():
    stream = StreamingSameCapture(24000)
    samples = np.ones(20, dtype=np.float32)
    stream.feed(samples)
    samples[:] = np.nan
    assert stream.buffered_samples == 20
    assert not stream.flush().truncated


def test_empty_capture():
    stream = StreamingSameCapture(24000)
    result = stream.flush()
    assert result.decoded_bytes == b""
    assert result.messages.alerts == ()


@pytest.mark.parametrize("rate,seconds", [(0, 5), (24000, 0), (24000, 121)])
def test_invalid_configuration(rate, seconds):
    with pytest.raises(ValueError):
        StreamingSameCapture(rate, max_seconds=seconds)


def test_nonfinite_input():
    with pytest.raises(ValueError):
        StreamingSameCapture(24000).feed(np.array([np.inf]))
