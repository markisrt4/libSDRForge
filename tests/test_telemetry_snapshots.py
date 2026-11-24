"""Hardware-free telemetry snapshot contract tests."""

import json

import numpy as np
import pytest

from sdrforge.telemetry.snapshots import receiver_snapshot, spectrum_snapshot


def test_spectrum_bin_metadata_and_nonfinite_values() -> None:
    payload = spectrum_snapshot(
        np.array([-30.0, float("nan"), -10.0, float("inf")]),
        center_frequency_hz=104_300_000,
        sample_rate_hz=200_000,
        timestamp_ns=123,
    )
    assert payload["bin_count"] == 4
    assert payload["first_bin_frequency_hz"] == 104_200_000
    assert payload["bin_spacing_hz"] == 50_000
    assert payload["power_db"] == [-30.0, None, -10.0, None]
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_invalid_spectrum() -> None:
    with pytest.raises(ValueError):
        spectrum_snapshot(np.array([]), center_frequency_hz=100, sample_rate_hz=200)


def test_receiver_tmc_remains_diagnostic_only() -> None:
    class Receiver:
        channel_frequency_hz = 94_700_000
        stereo_locked = True
        stereo_blend = 0.9
        rds_status = None
        last_rds_groups = ()

        @property
        def tmc_candidate_report(self) -> dict:
            return {"candidate_count": 3, "structurally_complete_unverified": 2}

    payload = receiver_snapshot(Receiver(), timestamp_ns=456)
    assert payload["tmc_diagnostics"]["usable_for_navigation"] is False
    assert payload["tmc_diagnostics"]["candidate_count"] == 3
    assert payload["rds_group_count"] == 0
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize(
    "mode, bandwidth",
    [
        ("NFM", 7_500),
        ("NFM", 12_500),
        ("AM", 6_000),
        ("AM", 10_000),
    ],
)
def test_non_wfm_receiver_status_has_no_fake_stereo_or_rds(mode, bandwidth) -> None:
    class Receiver:
        pass

    payload = receiver_snapshot(
        Receiver(),
        mode=mode,
        bandwidth_hz=bandwidth,
        frequency_hz=162_550_000,
        running=True,
        timestamp_ns=789,
    )
    assert payload["mode"] == mode
    assert payload["bandwidth_hz"] == bandwidth
    assert payload["channel_frequency_hz"] == 162_550_000
    assert payload["running"] is True
    assert payload["stereo_locked"] is None
    assert payload["stereo_blend"] is None
    assert payload["rds"] is None
    assert payload["rds_group_count"] == 0
    assert payload["tmc_diagnostics"] is None
    json.dumps(payload, allow_nan=False)


def test_wfm_receiver_status_preserves_legacy_metadata() -> None:
    class Receiver:
        channel_frequency_hz = 104_300_000
        stereo_locked = True
        stereo_blend = 0.75
        rds_status = None
        last_rds_groups = ()
        tmc_candidate_report = None

    payload = receiver_snapshot(
        Receiver(),
        mode="WFM",
        bandwidth_hz=200_000,
        timestamp_ns=123,
    )
    assert payload["mode"] == "WFM"
    assert payload["bandwidth_hz"] == 200_000
    assert payload["channel_frequency_hz"] == 104_300_000
    assert payload["stereo_locked"] is True
    assert payload["stereo_blend"] == 0.75
