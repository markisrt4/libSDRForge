# SPDX-License-Identifier: MIT
"""Hardware-free wire contract consumed by OpenRoadCode native RF UI."""

import json
from types import SimpleNamespace

import numpy as np

from sdrforge.telemetry.snapshots import receiver_snapshot, spectrum_snapshot


def test_orc_spectrum_wire_contract():
    payload = spectrum_snapshot(
        np.array([-80.0, float("nan"), -35.0]),
        center_frequency_hz=104_300_000,
        sample_rate_hz=2_400_000,
        timestamp_ns=123,
    )
    decoded = json.loads(json.dumps(payload, allow_nan=False))
    assert decoded["center_frequency_hz"] == 104_300_000
    assert decoded["sample_rate_hz"] == 2_400_000
    assert decoded["bin_count"] == 3
    assert decoded["power_db"] == [-80.0, None, -35.0]


def test_orc_receiver_wire_contract_and_stop_status():
    receiver = SimpleNamespace(
        channel_frequency_hz=104_300_000,
        stereo_locked=True,
        stereo_blend=1.0,
        rds_status=None,
        last_rds_groups=(),
        tmc_candidate_report=None,
    )
    running = receiver_snapshot(receiver, mode="WFM", running=True, timestamp_ns=123)
    stopped = receiver_snapshot(receiver, mode="WFM", running=False, timestamp_ns=124)
    for payload in (running, stopped):
        decoded = json.loads(json.dumps(payload, allow_nan=False))
        assert decoded["channel_frequency_hz"] == 104_300_000
        assert decoded["mode"] == "WFM"
        assert isinstance(decoded["running"], bool)
    assert running["running"] is True
    assert stopped["running"] is False
