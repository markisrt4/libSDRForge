"""Synthetic RF-to-aircraft tests, no SDR device required."""
import numpy as np
import pytest

from sdrforge.adsb.iq_demodulator import demodulate_frames
from sdrforge.adsb.iq_synthetic import synthesize_iq
from sdrforge.adsb.receiver_cli import SYNTHETIC_FRAMES
from sdrforge.adsb.receiver_session import AdsbReceiverSession


@pytest.mark.parametrize("sample_rate", [2e6, 2.4e6])
def test_known_frames_roundtrip(sample_rate):
    frames = tuple(bytes.fromhex(x) for x in SYNTHETIC_FRAMES)
    iq = synthesize_iq(frames, sample_rate)
    assert demodulate_frames(iq, sample_rate) == frames


@pytest.mark.parametrize("sample_rate", [2e6, 2.4e6])
def test_rf_to_aircraft_position(sample_rate):
    frames = tuple(bytes.fromhex(x) for x in SYNTHETIC_FRAMES[:2])
    iq = synthesize_iq(frames, sample_rate, noise=.01, seed=7)
    session = AdsbReceiverSession()
    for frame in demodulate_frames(iq, sample_rate):
        session.accept(frame, 1.0)
    stats = session.statistics(1.0)
    assert stats.frames_valid == 2
    assert stats.position_fixes == 1


def test_crc_corruption_rejected_by_session():
    raw = bytearray.fromhex(SYNTHETIC_FRAMES[0])
    raw[6] ^= 1
    iq = synthesize_iq((bytes(raw),))
    session = AdsbReceiverSession()
    for frame in demodulate_frames(iq, 2e6):
        session.accept(frame, 0)
    assert session.statistics(0).frames_valid == 0


def test_noise_and_invalid_inputs():
    assert demodulate_frames(np.zeros(1000, dtype=np.complex64), 2e6) == ()
    with pytest.raises(ValueError):
        demodulate_frames(np.zeros(100), 1e6)
    with pytest.raises(ValueError):
        synthesize_iq((b"short",))
