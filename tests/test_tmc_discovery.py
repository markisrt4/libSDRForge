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

def test_tmc_oda_application_id_requires_validated_3a() -> None:
    scanner = TmcDiscovery()
    scanner.process(group(0x1234, 0x8000, 0x0000, 0xCD46))
    assert not scanner.status.tmc_aid_seen
    scanner.process(group(0x1234, 0x3000, 0x0000, 0xCD46))
    assert scanner.status.tmc_aid_seen
    assert scanner.status.oda_app_ids == (0xCD46,)
    scanner.process(group(0x5678, 0x0000))
    assert not scanner.status.tmc_aid_seen
    assert scanner.status.oda_app_ids == ()


@pytest.mark.parametrize("changes", [
    {"synchronization": "pi_anchors", "corrected_bits": 1},
    {"synchronization": "soft"},
    {"corrected_bits": 1},
    {"uncertain_bits": 2},
])
def test_experimental_groups_cannot_enter_trusted_tmc(changes: dict) -> None:
    scanner = TmcDiscovery()
    scanner.process(group(0x1234, 0x0000))
    candidate = RdsGroup(0x5678, 0x3000, 0, 0xCD46, False, **changes)
    scanner.process(candidate)
    scanner.process(RdsGroup(0x5678, 0x8000, 0xAAAA, 0xBBBB, False, **changes))
    status = scanner.status
    assert status.pi == 0x1234
    assert status.total_groups == 1
    assert status.group_8a_count == 0
    assert status.group_3a_count == 0
    assert not status.tmc_aid_seen


def test_tmc_sequence_requires_current_station_oda_evidence() -> None:
    """A complete discovery sequence is station-local and never decodes events."""
    scanner = TmcDiscovery()
    pi = 0x5BDB
    scanner.process(group(pi, 0x8000, 0x1234, 0x5678))
    assert scanner.status.group_8a_count == 1
    assert not scanner.status.tmc_aid_seen

    scanner.process(group(pi, 0x3000, 0x0000, 0xCD46))
    scanner.process(group(pi, 0x8001, 0xAAAA, 0xBBBB))
    status = scanner.status
    assert status.pi == pi
    assert status.tmc_aid_seen
    assert status.oda_app_ids == (0xCD46,)
    assert status.group_3a_count == 1
    assert status.group_8a_count == 2
    assert status.raw_8a == ((0x8000, 0x1234, 0x5678), (0x8001, 0xAAAA, 0xBBBB))

    # New station: previous station's 3A evidence must not carry over.
    scanner.process(group(0x1234, 0x8000, 0x0001, 0x0002))
    assert scanner.status.pi == 0x1234
    assert scanner.status.group_8a_count == 1
    assert scanner.status.group_3a_count == 0
    assert not scanner.status.tmc_aid_seen
    assert scanner.status.oda_app_ids == ()
