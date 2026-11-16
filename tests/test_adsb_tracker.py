"""CPR reference vectors and deterministic aircraft tracking tests."""
import pytest

from sdrforge.adsb import decode_message
from sdrforge.adsb.cpr import decode_global
from sdrforge.adsb.tracker import AircraftTracker


EVEN = "8D40621D58C382D690C8AC2863A7"
ODD = "8D40621D58C386435CC412692AD6"


def test_global_cpr_known_airborne_pair():
    even, odd = decode_message(EVEN), decode_message(ODD)
    assert even is not None and odd is not None
    assert even.cpr_odd is False
    assert odd.cpr_odd is True
    lat, lon = decode_global(even.cpr_lat, even.cpr_lon, odd.cpr_lat, odd.cpr_lon,
                             most_recent_odd=True)
    assert lat == pytest.approx(52.26578, abs=0.0001)
    assert lon == pytest.approx(3.93891, abs=0.0001)


def test_tracker_combines_frames_and_expires():
    tracker = AircraftTracker(ttl_seconds=20)
    first = tracker.update(decode_message(EVEN), 0)
    assert first.latitude is None
    second = tracker.update(decode_message(ODD), 5)
    assert second.latitude == pytest.approx(52.26578, abs=0.0001)
    assert second.altitude_ft == 38000
    assert len(tracker.snapshot(24)) == 1
    assert tracker.snapshot(26) == ()


def test_stale_cpr_pair_is_not_combined():
    tracker = AircraftTracker(cpr_pair_seconds=10)
    tracker.update(decode_message(EVEN), 0)
    result = tracker.update(decode_message(ODD), 11)
    assert result.latitude is None


def test_monotonic_clock_and_invalid_timeout():
    with pytest.raises(ValueError):
        AircraftTracker(ttl_seconds=0)
    tracker = AircraftTracker()
    tracker.update(decode_message(EVEN), 10)
    with pytest.raises(ValueError):
        tracker.snapshot(9)


def test_cpr_rejects_out_of_range_fraction():
    with pytest.raises(ValueError):
        decode_global(131072, 0, 0, 0, most_recent_odd=False)
