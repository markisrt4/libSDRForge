"""End-to-end SAME header tests with deliberately offset transmitter clocks.

The exact transmitter rate is supplied as the candidate here. These tests
do not yet prove automatic rate estimation or robust RF reception.
"""

import numpy as np
import pytest

from sdrforge.weather.same_afsk import (
    BAUD,
    decode_same_audio,
    synthesize_same_audio,
)

HEADER = b"ZCZC-WXR-RWT-026099+0030-3211200-KDTX/NWS-"


@pytest.mark.parametrize("baud_error", [-1.0, -0.5, 0.5, 1.0])
def test_complete_header_with_transmitter_clock_error(baud_error):
    audio = synthesize_same_audio(HEADER, baud=BAUD + baud_error)
    decoded = decode_same_audio(audio, 24000, baud_offsets=(baud_error,))
    assert HEADER in decoded


@pytest.mark.parametrize("leading_samples", [1, 13, 29])
def test_complete_header_with_unaligned_start(leading_samples):
    audio = synthesize_same_audio(HEADER)
    shifted = np.pad(audio, (leading_samples, 0))
    assert HEADER in decode_same_audio(shifted, 24000)


def test_generator_rejects_nonfinite_baud():
    with pytest.raises(ValueError):
        synthesize_same_audio(HEADER, baud=float("nan"))


def test_generator_rejects_zero_baud():
    with pytest.raises(ValueError):
        synthesize_same_audio(HEADER, baud=0)


def test_generator_rejects_impossibly_fast_baud():
    with pytest.raises(ValueError):
        synthesize_same_audio(HEADER, baud=4000)
