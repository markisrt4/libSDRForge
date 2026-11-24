"""Synthetic chunked SAME burst detection tests."""

import numpy as np
import pytest

from sdrforge.weather.same_afsk import synthesize_same_audio
from sdrforge.weather.same_burst import SameBurstDetector

HEADER = b"ZCZC-WXR-RWT-026099+0030-3211200-KDTX/NWS-"


def _signal(payloads):
    gap = np.zeros(24000 // 2, dtype=np.float32)
    parts = [gap]
    for payload in payloads:
        parts.extend((synthesize_same_audio(payload), gap))
    return np.concatenate(parts)


def test_two_bursts_confirm_alert_across_irregular_chunks():
    audio = _signal([HEADER, HEADER])
    detector = SameBurstDetector(24000)
    for index in range(0, len(audio), 777):
        detector.feed(audio[index : index + 777])
    result = detector.finish()
    assert len(result.alerts) == 1
    assert result.alerts[0].event == "RWT"


def test_one_burst_not_confirmed():
    detector = SameBurstDetector(24000)
    detector.feed(_signal([HEADER]))
    assert detector.finish().alerts == ()


def test_silence_no_alert():
    detector = SameBurstDetector(24000)
    detector.feed(np.zeros(24000, dtype=np.float32))
    assert detector.finish().alerts == ()


def test_reset_after_finish():
    detector = SameBurstDetector(24000)
    detector.feed(_signal([HEADER, HEADER]))
    assert len(detector.finish().alerts) == 1
    assert detector.finish().alerts == ()


def test_truncated_burst_not_confirmed():
    detector = SameBurstDetector(24000, max_burst_seconds=0.2)
    detector.feed(_signal([HEADER, HEADER]))
    assert detector.finish().alerts == ()


def test_reject_nan():
    with pytest.raises(ValueError):
        SameBurstDetector(24000).feed(np.array([np.nan]))


def test_bad_threshold():
    with pytest.raises(ValueError):
        SameBurstDetector(24000, threshold_rms=0)
