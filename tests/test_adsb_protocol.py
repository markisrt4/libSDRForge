"""Hardware-independent Mode S / ADS-B protocol tests."""
import pytest

from sdrforge.adsb import append_crc, decode_message, modes_crc


def test_known_airborne_position_frame():
    # Widely used DF17 example frame with Q-bit altitude and CPR payload.
    raw = bytes.fromhex("8D40621D58C382D690C8AC2863A7")
    msg = decode_message(raw)
    assert msg is not None
    assert msg.icao == "40621D"
    assert msg.type_code == 11
    assert msg.altitude_ft == 38000
    assert msg.cpr_odd is False
    assert msg.cpr_lat is not None
    assert msg.cpr_lon is not None
    assert modes_crc(raw) == 0


def test_known_identification_frame():
    msg = decode_message("8D4840D6202CC371C32CE0576098")
    assert msg is not None
    assert msg.icao == "4840D6"
    assert msg.callsign == "KLM1023"


def test_known_velocity_frame():
    msg = decode_message("8D485020994409940838175B284F")
    assert msg is not None
    assert msg.type_code == 19
    assert msg.speed_kt is not None
    assert msg.heading_deg is not None


def test_corrupted_crc_is_rejected():
    raw = bytearray.fromhex("8D40621D58C382D690C8AC2863A7")
    raw[6] ^= 1
    assert decode_message(bytes(raw)) is None


def test_reject_invalid_frames():
    assert decode_message("not hex") is None
    assert decode_message(b"") is None
    assert decode_message(bytes(14)) is None
    with pytest.raises(ValueError):
        modes_crc(bytes(3))


def test_crc_roundtrip():
    payload = bytes.fromhex("8D40621D58C382D690C8AC")
    frame = append_crc(payload)
    assert modes_crc(frame) == 0
    assert decode_message(frame) is not None
