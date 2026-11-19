"""Synthetic aircraft snapshots are deterministic and tracker-compatible."""
import pytest

from sdrforge.adsb.simulation import simulated_aircraft


def test_deterministic_motion():
    assert simulated_aircraft(0, 3) == simulated_aircraft(0, 3)
    assert simulated_aircraft(1, 3) != simulated_aircraft(0, 3)


def test_snapshot_fields():
    aircraft = simulated_aircraft(0, 1)[0]
    assert aircraft["icao"] == "A00000"
    assert aircraft["heading_deg"] == pytest.approx(90)
    assert 0 < aircraft["altitude_ft"] < 10000
    assert -90 <= aircraft["latitude"] <= 90


def test_invalid_count():
    with pytest.raises(ValueError):
        simulated_aircraft(0, -1)
