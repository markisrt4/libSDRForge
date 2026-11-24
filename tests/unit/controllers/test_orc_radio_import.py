# SPDX-License-Identifier: MIT
"""No-hardware tests for the explicit ORC radio migration."""

import json

import pytest

from sdrforge.adapters.factory_radio_catalog import load_factory_radio_catalog
from sdrforge.adapters.json_preset_store import JsonPresetStore
from sdrforge.adapters.orc_radio_import import (
    import_orc_radio_data,
    persist_imported_user_presets,
)


def _profile(label):
    return {
        "key": "fm_radio",
        "label": label,
        "default_mode": {"name": "WFM", "bandwidth": 180000, "step_hz": 100000},
        "range": {
            "min_frequency_hz": 87500000,
            "max_frequency_hz": 108000000,
            "start_frequency_hz": 88100000,
        },
        "presets": [{"label": "Factory", "frequency_hz": 94700000}],
    }


def test_factory_profiles_ship_without_orc():
    catalog, presets = load_factory_radio_catalog()
    assert catalog.profile("fm_radio").group == "FM"
    assert catalog.profile("weather_band").group == "WEATHER"
    assert len([p for p in presets if p.profile_key == "weather_band"]) == 7


def test_locale_override_and_idempotent_user_import(tmp_path):
    root = tmp_path / "radio"
    for name, label in (("common", "Common"), ("custom", "Local")):
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "fm_radio.json").write_text(json.dumps(_profile(label)))
    user_path = tmp_path / "radio_presets.json"
    user_path.write_text(
        json.dumps({"fm_radio": [{"label": "Favorite", "frequency_hz": 104300000}]})
    )
    data = import_orc_radio_data(root, locale="custom", user_presets_path=user_path)
    assert data.catalog.profile("fm_radio").label == "Local"
    assert len(data.factory_presets) == 1
    assert len(data.user_presets) == 1
    store = JsonPresetStore(tmp_path / "sdrforge.json")
    assert persist_imported_user_presets(data, store) == 1
    assert persist_imported_user_presets(data, store) == 0
    assert store.list_presets() == data.user_presets
    assert user_path.exists()


def test_no_implicit_locale(tmp_path):
    root = tmp_path / "radio"
    for name, label in (("common", "Common"), ("romeo", "Romeo")):
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "fm_radio.json").write_text(json.dumps(_profile(label)))
    assert import_orc_radio_data(root).catalog.profile("fm_radio").label == "Common"


def test_reject_unsafe_locale(tmp_path):
    with pytest.raises(ValueError, match="locale"):
        import_orc_radio_data(tmp_path, locale="../other")
