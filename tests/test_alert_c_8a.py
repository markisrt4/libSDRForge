# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""ALERT-C message structure regression tests using WOMC capture groups."""
from sdrforge.protocols.rds.alert_c_8a import parse_alert_c_8a
from sdrforge.protocols.rds.rds_block_sync import RdsGroup


def group(raw: str) -> RdsGroup:
    a, b, c, d = (int(word, 16) for word in raw.split())
    return RdsGroup(a, b, c, d, False, synchronization="redsea_fec_unknown")


def test_womc_first_group() -> None:
    result = parse_alert_c_8a(group("7ADA 80E1 8846 0DFC"))
    assert result is not None
    assert result.kind == "multi_first"
    assert result.continuity_index == 1
    assert result.event_code == (0x8846 & 0x7FF)
    assert result.location_code_raw == 0x0DFC
    assert result.synchronization == "redsea_fec_unknown"


def test_womc_continuation() -> None:
    result = parse_alert_c_8a(group("7ADA 80E3 0440 0000"))
    assert result is not None
    assert result.kind == "multi_continuation"
    assert result.continuity_index == 3
    assert result.event_code is None
    assert result.location_code_raw is None


def test_non_tmc_group_ignored() -> None:
    assert parse_alert_c_8a(group("7ADA 20E1 8846 0DFC")) is None


def test_single_group_layout() -> None:
    result = parse_alert_c_8a(group("7ADA 80E9 8846 0DFC"))
    assert result is not None
    assert result.kind == "single"
    assert result.duration == 1
    assert result.diversion is True
    assert result.continuity_index is None
