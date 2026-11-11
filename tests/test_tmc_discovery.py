# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Deterministic offline checks for RDS-TMC discovery."""

import pytest

from sdrforge.protocols.rds.rds_block_sync import RdsGroup
from sdrforge.protocols.rds.tmc_discovery import TmcDiscovery


def group(pi: int, b: int, c: int = 0, d: int = 0) -> RdsGroup:
    return RdsGroup(pi, b, c, d, False)


def test_observes_tmc_and_oda_without_claiming_decoded_events() -> None:
    scanner = TmcDiscovery(max_raw_groups=1)
    scanner.process(group(0x1234, 0x8000, 0xAAAA, 0xBBBB))
    scanner.process(group(0x1234, 0x8001, 0xCCCC, 0xDDDD))
    scanner.process(group(0x1234, 0x3000))
    scanner.process(group(0x1234, 0x0410))
    status = scanner.status
    assert status.pi == 0x1234
    assert status.total_groups == 4
    assert status.group_8a_count == 2
    assert status.group_3a_count == 1
    assert status.group_0a_tp_count == 1
    assert status.group_0a_ta_count == 1
    assert status.raw_8a == ((0x8000, 0xAAAA, 0xBBBB),)


def test_station_change_resets_counts() -> None:
    scanner = TmcDiscovery()
    scanner.process(group(1, 0x8000))
    scanner.process(group(2, 0x0000))
    assert scanner.status.pi == 2
    assert scanner.status.group_8a_count == 0
    assert scanner.status.total_groups == 1


def test_validation() -> None:
    with pytest.raises(ValueError):
        TmcDiscovery(max_raw_groups=-1)
    with pytest.raises(TypeError):
        TmcDiscovery().process(None)  # type: ignore[arg-type]
