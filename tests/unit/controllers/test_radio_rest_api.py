# SPDX-License-Identifier: MIT
"""Hardware-free radio REST dispatcher tests."""
from sdrforge.adapters.json_preset_store import JsonPresetStore
from sdrforge.controllers.radio_catalog import PresetService, RadioCatalog
from sdrforge.interfaces.radio_catalog_if import RadioMode, RadioProfile
from sdrforge.protocols.rest.radio_api import RadioApi


def _api(tmp_path):
    catalog = RadioCatalog((RadioProfile(
        "fm_radio", "FM Radio", "FM", 87500000, 108000000,
        88100000, RadioMode("WFM", 180000, 100000),
    ),))
    return RadioApi(catalog, PresetService(
        catalog, JsonPresetStore(tmp_path / "presets.json"),
    ))


def test_profiles_and_unknown_profile(tmp_path):
    api = _api(tmp_path)
    status, payload = api.dispatch("GET", "/v1/radio/profiles")
    assert status == 200
    assert payload["profiles"][0]["key"] == "fm_radio"
    status, payload = api.dispatch("GET", "/v1/radio/profiles/fm_radio")
    assert status == 200
    assert payload["profile"]["group"] == "FM"
    assert api.dispatch("GET", "/v1/radio/profiles/unknown")[0] == 400


def test_preset_crud_and_owner_filter(tmp_path):
    api = _api(tmp_path)
    status, result = api.dispatch("POST", "/v1/radio/presets", {
        "profile_key": "fm_radio", "label": "A",
        "frequency_hz": 104300000, "owner": "driver",
    })
    assert status == 201
    preset_id = result["preset"]["id"]
    assert len(api.dispatch("GET", "/v1/radio/presets?owner=driver")[1]["presets"]) == 1
    assert api.dispatch("GET", "/v1/radio/presets?owner=guest")[1]["presets"] == []
    assert api.dispatch("PATCH", f"/v1/radio/presets/{preset_id}", {
        "owner": "guest", "label": "X",
    })[0] == 404
    status, result = api.dispatch("PATCH", f"/v1/radio/presets/{preset_id}", {
        "owner": "driver", "label": "Updated",
    })
    assert status == 200
    assert result["preset"]["label"] == "Updated"
    assert api.dispatch("DELETE", f"/v1/radio/presets/{preset_id}", {
        "owner": "driver",
    })[0] == 200
    assert api.dispatch("GET", "/v1/radio/presets")[1]["presets"] == []


def test_invalid_frequency_and_mode(tmp_path):
    api = _api(tmp_path)
    assert api.dispatch("POST", "/v1/radio/presets", {
        "profile_key": "fm_radio", "label": "bad",
        "frequency_hz": 162550000,
    })[0] == 400
    assert api.dispatch("POST", "/v1/radio/presets", {
        "profile_key": "fm_radio", "label": "bad",
        "frequency_hz": 104300000,
        "mode": {"name": "UNKNOWN", "bandwidth_hz": 0, "step_hz": 1},
    })[0] == 400
