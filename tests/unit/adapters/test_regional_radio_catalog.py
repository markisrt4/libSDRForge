# SPDX-License-Identifier: MIT
"""Regional overlay preserves packaged defaults and user storage."""

import json

import pytest

from sdrforge.adapters.regional_radio_catalog import load_radio_catalog


def test_default_catalog_is_locale_neutral():
    catalog, presets = load_radio_catalog()
    assert catalog.profile("fm_radio").key == "fm_radio"
    assert not any(p.profile_key == "fm_radio" for p in presets)


def test_overlay_replaces_matching_factory_presets_and_adds_new_profile(tmp_path):
    common = tmp_path / "common"
    common.mkdir()
    local = tmp_path / "romeo"
    local.mkdir()
    profile = {
        "key": "fm_radio",
        "label": "Regional FM",
        "range": {
            "min_frequency_hz": 87500000,
            "max_frequency_hz": 108000000,
            "start_frequency_hz": 94700000,
        },
        "default_mode": {"name": "WFM", "bandwidth": 180000, "step_hz": 100000},
        "presets": [{"label": "94.7", "frequency_hz": 94700000}],
    }
    (local / "fm_radio.json").write_text(json.dumps(profile), encoding="utf-8")
    catalog, presets = load_radio_catalog(radio_root=tmp_path, locale="romeo")
    assert catalog.profile("fm_radio").label == "Regional FM"
    assert [p.frequency_hz for p in presets if p.profile_key == "fm_radio"] == [94700000]
    assert any(p.profile_key == "weather_band" for p in presets)
    assert any(p.profile_key == "police_fire" for p in presets)
    assert all(p.origin == "factory" for p in presets)


def test_unknown_locale_requires_root():
    with pytest.raises(ValueError, match="radio_root"):
        load_radio_catalog(locale="unknown")


def test_packaged_romeo_catalog_is_complete():
    catalog, presets = load_radio_catalog(locale="romeo")
    assert len(catalog.profiles()) == 11
    assert len(presets) == 136
    assert catalog.profile("fm_radio").default_mode.step_hz == 200000
    assert len({p.id for p in presets}) == len(presets)
    assert all(p.origin == "factory" for p in presets)
