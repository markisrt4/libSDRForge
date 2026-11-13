# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Station PI identity confirmation tests."""

from sdrforge.protocols.rds.station_identity_cache import StationIdentityCache


def test_requires_three_matching_groups():
    cache = StationIdentityCache()
    assert cache.observe(0x5BDB, 94_700_000) is None
    assert cache.observe(0x5BDB, 94_700_000) is None
    assert cache.current is None
    assert cache.observe(0x5BDB, 94_700_000) == "identified"
    assert cache.current.pi == 0x5BDB


def test_single_stray_pi_does_not_change_station():
    cache = StationIdentityCache(2)
    cache.observe(0x5BDB, 94_700_000)
    cache.observe(0x5BDB, 94_700_000)
    assert cache.observe(0x1234, 94_700_000) is None
    assert cache.observe(0x5BDB, 94_700_000) is None
    assert cache.current.pi == 0x5BDB


def test_confirmed_change():
    cache = StationIdentityCache(2)
    cache.observe(0x5BDB, 94_700_000)
    cache.observe(0x5BDB, 94_700_000)
    assert cache.observe(0x1234, 94_700_000) is None
    assert cache.observe(0x1234, 94_700_000) == "changed"
    assert cache.current.pi == 0x1234


def test_ps_and_frequency_refresh_without_identity_change():
    cache = StationIdentityCache(1)
    cache.observe(0x5BDB, 94_700_000)
    assert cache.observe(0x5BDB, 95_000_000, "WCSX") is None
    assert cache.current.program_service == "WCSX"
    assert cache.current.frequency_hz == 95_000_000
