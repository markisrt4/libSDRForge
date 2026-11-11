"""Hardware-independent tests for the public FM convenience constructor."""

import pytest

from sdrforge import RadioSession


@pytest.mark.parametrize("frequency", [87.5, 104.3, 108.0])
def test_fm_frequency_conversion(frequency):
    radio = RadioSession.fm(frequency)
    assert radio.frequency_hz == round(frequency * 1_000_000)
    assert radio.gain_db is None
    assert radio.rf_warmup_seconds == 2.0


@pytest.mark.parametrize("frequency", [0, 87.4, 108.1, float("nan"), float("inf")])
def test_fm_rejects_invalid_frequency(frequency):
    with pytest.raises(ValueError, match="FM frequency"):
        RadioSession.fm(frequency)


def test_fm_mono_and_rds_validation():
    radio = RadioSession.fm(104.3, stereo=False, gain_db=29.7,
                            rf_warmup_seconds=0)
    assert radio.gain_db == 29.7
    assert radio.rf_warmup_seconds == 0
    with pytest.raises(ValueError, match="RDS requires stereo"):
        RadioSession.fm(104.3, stereo=False, rds=True)


def test_fm_accepts_injected_source():
    source = object()
    radio = RadioSession.fm(104.3, source=source)
    assert radio.source is source
