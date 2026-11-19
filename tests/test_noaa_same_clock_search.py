"""Symbol-rate search regression tests without RF hardware."""
import numpy as np
import pytest

from sdrforge.weather import same_afsk

HEADER = b"ZCZC-WXR-RWT-026099+0030-3211200-KDTX/NWS-"


def test_nominal_rate_search_decodes_complete_header():
    audio = same_afsk.synthesize_same_audio(HEADER)
    assert HEADER in same_afsk.decode_same_audio(audio, 24000, baud_offsets=(0.0,))


def test_multiple_candidate_rates_preserve_nominal_decode():
    audio = same_afsk.synthesize_same_audio(HEADER)
    assert HEADER in same_afsk.decode_same_audio(
        audio, 24000, baud_offsets=(-1.0, 0.0, 1.0))


def test_symbol_rate_changes_bit_window_count():
    audio = np.zeros(24000, dtype=np.float32)
    slow = same_afsk._classify_bits(audio, 24000, 0, same_afsk.BAUD - 2)
    fast = same_afsk._classify_bits(audio, 24000, 0, same_afsk.BAUD + 2)
    assert len(fast) > len(slow)


@pytest.mark.parametrize("offsets", [(), (float("nan"),), (float("inf"),),
                                      (-same_afsk.BAUD,), (-1000.0,)])
def test_invalid_symbol_rates_rejected(offsets):
    with pytest.raises(ValueError):
        same_afsk.decode_same_audio(np.zeros(480), 24000, baud_offsets=offsets)


def test_default_matches_explicit_nominal():
    audio = same_afsk.synthesize_same_audio(b"ZCZC")
    assert same_afsk.decode_same_audio(audio, 24000) == (
        same_afsk.decode_same_audio(audio, 24000, baud_offsets=(0.0,)))
