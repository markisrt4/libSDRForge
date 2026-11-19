"""Frame-level ADS-B receiver diagnostics."""
from sdrforge.adsb.receiver_cli import SYNTHETIC_FRAMES, main
from sdrforge.adsb.receiver_session import AdsbReceiverSession


def test_valid_cpr_pair_tracks_position():
    session = AdsbReceiverSession()
    session.accept(SYNTHETIC_FRAMES[0], 0)
    session.accept(SYNTHETIC_FRAMES[1], 1)
    stats = session.statistics(1)
    assert stats.frames_valid == 2
    assert stats.aircraft_tracked == 1
    assert stats.position_fixes == 1


def test_corrupt_crc_and_unsupported_frames():
    session = AdsbReceiverSession()
    raw = bytearray.fromhex(SYNTHETIC_FRAMES[0])
    raw[6] ^= 1
    assert session.accept(raw, 0) is None
    assert session.accept(b"", 0) is None
    stats = session.statistics(0)
    assert stats.crc_failures == 1
    assert stats.unsupported_frames == 1


def test_synthetic_cli_reports_statistics(capsys):
    assert main(["--source", "synthetic", "--cycles", "2"]) == 0
    output = capsys.readouterr().out
    assert '"frames_valid": 8' in output
    assert '"position_fixes": 1' in output


def test_session_expiry():
    session = AdsbReceiverSession(ttl_seconds=5)
    session.accept(SYNTHETIC_FRAMES[0], 0)
    assert session.statistics(6).aircraft_tracked == 0
