# SPDX-License-Identifier: MIT
"""Offline IQ source preserves sample boundaries and recorded drop gaps."""

import json

from sdrforge.adapters.recorded_iq import RecordedIqSource


def test_recorded_iq_replays_and_reports_gaps(tmp_path):
    path = tmp_path / "sample.iq"
    path.write_bytes(bytes(range(16)))
    path.with_suffix(".iq.json").write_text(json.dumps({
        "format": "rtl_u8_interleaved_iq",
        "center_frequency_hz": 94_700_000,
        "sample_rate_hz": 2_400_000,
        "gaps": [{"sample_offset": 4, "dropped_blocks": 2}],
    }))
    source = RecordedIqSource(path, block_bytes=16)
    source.open()
    source.start()
    assert source.get_center_frequency() == 94_700_000
    first = source.read_iq()
    assert first is not None and first.samples == bytes(range(8))
    assert source.get_acquisition_stats()["dropped_blocks"] == 0
    second = source.read_iq()
    assert second is not None and second.samples == bytes(range(8, 16))
    assert source.get_acquisition_stats()["dropped_blocks"] == 2
    assert source.read_iq() is None
    source.close()

def test_recorded_iq_rewind_resets_gap_tracking(tmp_path):
    path = tmp_path / "rewind.iq"
    path.write_bytes(bytes(range(16)))
    path.with_suffix(".iq.json").write_text(json.dumps({
        "format": "rtl_u8_interleaved_iq",
        "center_frequency_hz": 94_700_000,
        "sample_rate_hz": 2_400_000,
        "gaps": [{"sample_offset": 4, "dropped_blocks": 3}],
    }))
    source = RecordedIqSource(path, block_bytes=8)
    source.open()
    assert source.read_iq() is not None
    assert source.read_iq() is not None
    assert source.get_acquisition_stats()["dropped_blocks"] == 3
    source.rewind()
    assert source.get_acquisition_stats()["dropped_blocks"] == 0
    first = source.read_iq()
    assert first is not None and first.samples == bytes(range(8))
    source.close()
