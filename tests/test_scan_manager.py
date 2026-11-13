"""Simulated FM scanning tests without an SDR dongle."""
from threading import Event

from sdrforge.protocols.rds.station_catalog import StationCatalog

import pytest

from sdrforge.controllers.scan_manager import ScanManager
from sdrforge.models.scan_config import ScanConfig
from sdrforge.simulation.simulated_signal_scanner import SimulatedSignalScanner


def test_fm_scan_finds_only_strong_stations() -> None:
    scanner = SimulatedSignalScanner({
        88_100_000: -68.0,
        88_200_000: -87.0,
        88_300_000: -75.0,
    })
    progress = []
    result = ScanManager(scanner).scan(
        ScanConfig(88_100_000, 88_300_000, 100_000, 8.0),
        progress=lambda done, total: progress.append((done, total)),
    )
    assert [item.frequency_hz for item in result] == [88_100_000, 88_300_000]
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert result[0].margin_db == 22.0


def test_scan_cancellation() -> None:
    stop = Event()
    measurements = []

    def on_progress(done: int, total: int) -> None:
        measurements.append(done)
        stop.set()

    result = ScanManager(SimulatedSignalScanner({88_100_000: -65.0})).scan(
        ScanConfig(88_100_000, 88_500_000),
        cancel=stop,
        progress=on_progress,
    )
    assert len(result) == 1
    assert measurements == [1]


def test_scan_already_cancelled() -> None:
    stop = Event()
    stop.set()
    result = ScanManager(SimulatedSignalScanner({})).scan(
        ScanConfig(88_100_000, 88_500_000), cancel=stop,
    )
    assert result == []


@pytest.mark.parametrize("settings", [
    {"start_hz": 0},
    {"start_hz": 108_000_000, "stop_hz": 87_500_000},
    {"step_hz": 0},
    {"modulation": "INVALID"},
])
def test_invalid_scan_config(settings: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ScanConfig(**settings)


def test_scan_persists_rf_discoveries_without_inventing_rds_identity(tmp_path):
    path = tmp_path / "stations.json"
    config = ScanConfig(88_100_000, 88_300_000, 100_000, 8.0)
    scanner = ScanManager(SimulatedSignalScanner({
        88_100_000: -68.0, 88_200_000: -87.0, 88_300_000: -75.0,
    }))
    scanner.scan(config, catalog=StationCatalog(path))
    entries = StationCatalog(path).stations
    assert len(entries) == 2
    assert all(entry["pi"] is None for entry in entries.values())
    assert all(entry["scan_observations"] == 1 for entry in entries.values())
    scanner.scan(config, catalog=StationCatalog(path))
    entries = StationCatalog(path).stations
    assert len(entries) == 2
    assert all(entry["scan_observations"] == 2 for entry in entries.values())
