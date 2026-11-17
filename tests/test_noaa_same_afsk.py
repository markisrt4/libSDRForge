"""Deterministic SAME waveform and conservative alert confirmation tests."""
import numpy as np
import pytest

from sdrforge.weather.same_afsk import decode_same_audio, synthesize_same_audio
from sdrforge.weather.same_messages import confirm_same_messages

HEADER = b"ZCZC-WXR-RWT-026099+0030-3211200-KDTX/NWS-"


def test_clean_afsk_decodes_same_header():
    audio = synthesize_same_audio(HEADER)
    decoded = decode_same_audio(audio, 24000)
    assert HEADER in decoded


def test_repeated_header_confirms_alert():
    messages = confirm_same_messages(HEADER + b"\x00" + HEADER)
    assert len(messages.alerts) == 1
    assert messages.alerts[0].event == "RWT"


def test_single_header_never_confirms():
    assert confirm_same_messages(HEADER).alerts == ()


def test_different_headers_do_not_confirm():
    assert confirm_same_messages(HEADER + HEADER.replace(b"RWT", b"TOR")).alerts == ()


def test_end_marker():
    assert confirm_same_messages(b"NNNN").end_of_message


def test_no_signal():
    assert decode_same_audio(np.array([], dtype=np.float32), 24000) == b""


@pytest.mark.parametrize("sample_rate", [0, 4000])
def test_invalid_rate(sample_rate):
    with pytest.raises(ValueError):
        decode_same_audio(np.zeros(100), sample_rate)


def test_invalid_audio():
    with pytest.raises(ValueError):
        decode_same_audio(np.array([np.nan]), 24000)


def test_invalid_confirmation_threshold():
    with pytest.raises(ValueError):
        confirm_same_messages(HEADER * 3, min_repeats=1)
