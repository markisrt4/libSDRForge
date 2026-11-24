# SPDX-License-Identifier: MIT
"""Packaged profiles stay hardware-independent and compatible with receiver modes."""
from sdrforge.adapters.factory_radio_catalog import load_factory_radio_catalog


def test_air_and_ham_profiles_are_packaged():
    catalog, presets = load_factory_radio_catalog()
    profiles = {profile.key: profile for profile in catalog.profiles()}
    assert {"fm_radio", "weather_band", "airband_am", "ham_2m", "ham_70cm"} <= profiles.keys()
    assert profiles["airband_am"].default_mode.name == "AM"
    assert profiles["airband_am"].default_mode.bandwidth_hz in (6000, 10000, 12500, 25000)
    assert profiles["ham_2m"].default_mode.name == "NFM"
    assert profiles["ham_70cm"].default_mode.name == "NFM"
    for preset in presets:
        profile = profiles[preset.profile_key]
        assert profile.minimum_frequency_hz <= preset.frequency_hz <= profile.maximum_frequency_hz
        assert preset.owner == "factory"
        assert preset.origin == "factory"


def test_factory_preset_ids_are_stable():
    _, first = load_factory_radio_catalog()
    _, second = load_factory_radio_catalog()
    assert [p.id for p in first] == [p.id for p in second]
    assert len({p.id for p in first}) == len(first)


def test_standard_scanner_profiles_are_packaged():
    catalog, presets = load_factory_radio_catalog()
    expected = {"cb": 40, "frs": 22, "gmrs": 8, "marine": 9, "railroad": 10}
    for key, count in expected.items():
        profile = catalog.profile(key)
        assert profile.group == "SCANNER"
        assert sum(p.profile_key == key for p in presets) == count
        assert profile.default_mode.name == ("AM" if key == "cb" else "NFM")
