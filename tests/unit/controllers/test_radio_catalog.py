# SPDX-License-Identifier: MIT
"""Hardware-free tests for canonical radio catalog and user presets."""

from dataclasses import replace

import pytest

from sdrforge.adapters.json_preset_store import JsonPresetStore
from sdrforge.controllers.radio_catalog import PresetService, RadioCatalog
from sdrforge.interfaces.radio_catalog_if import RadioMode, RadioProfile


@pytest.fixture
def service(tmp_path):
    mode = RadioMode("WFM", 180000, 100000)
    catalog = RadioCatalog(
        (
            RadioProfile(
                "fm_radio",
                "FM",
                "FM",
                87500000,
                108000000,
                88100000,
                mode,
            ),
        )
    )
    return PresetService(catalog, JsonPresetStore(tmp_path / "presets.json"))


def test_save_and_reload(service, tmp_path):
    preset = service.save(
        profile_key="fm_radio", label="  Favorite  ", frequency_hz=104300000
    )
    assert preset.label == "Favorite"
    assert preset.origin == "user"
    assert service.list_presets(owner="default") == (preset,)
    fresh = JsonPresetStore(tmp_path / "presets.json")
    assert fresh.list_presets() == (preset,)


def test_update_and_delete(service):
    preset = service.save(profile_key="fm_radio", label="A", frequency_hz=94700000)
    updated = service.update(replace(preset, label="B"))
    assert updated.label == "B"
    assert not service.delete(preset.id, owner="other")
    assert service.delete(preset.id, owner="default")
    assert service.list_presets() == ()


def test_invalid_frequency_rejected(service):
    with pytest.raises(ValueError, match="outside profile"):
        service.save(profile_key="fm_radio", label="Bad", frequency_hz=162550000)


def test_factory_preset_cannot_be_mutated(service):
    preset = service.save(profile_key="fm_radio", label="A", frequency_hz=104300000)
    with pytest.raises(ValueError, match="factory"):
        service.update(replace(preset, origin="factory"))


def test_profile_key_uniqueness():
    mode = RadioMode("NFM", 12500, 5000)
    profile = RadioProfile("ham_2m", "2m", "HAM", 144000000, 148000000, 146520000, mode)
    with pytest.raises(ValueError, match="duplicate"):
        RadioCatalog((profile, profile))
