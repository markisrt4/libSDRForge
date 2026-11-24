# SPDX-License-Identifier: MIT
"""Tests for live-server catalog configuration without SDR hardware."""

from sdrforge.adapters.factory_radio_catalog import load_factory_radio_catalog
from sdrforge.adapters.json_preset_store import JsonPresetStore
from sdrforge.adapters.preset_paths import default_preset_path
from sdrforge.controllers.radio_catalog import PresetService
from sdrforge.protocols.rest.radio_api import RadioApi


def test_default_preset_path_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("SDRFORGE_PRESETS_PATH", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_preset_path() == tmp_path / "sdrforge" / "radio_presets.json"


def test_explicit_preset_path_override(monkeypatch, tmp_path):
    path = tmp_path / "radio.json"
    monkeypatch.setenv("SDRFORGE_PRESETS_PATH", str(path))
    assert default_preset_path() == path


def test_factory_and_user_presets_share_read_endpoint(tmp_path):
    catalog, factory = load_factory_radio_catalog()
    api = RadioApi(
        catalog,
        PresetService(
            catalog,
            JsonPresetStore(tmp_path / "presets.json"),
        ),
        factory_presets=factory,
    )
    status, response = api.dispatch("GET", "/v1/radio/presets?profile_key=weather_band")
    assert status == 200
    assert len(response["presets"]) == 7
    assert all(p["origin"] == "factory" for p in response["presets"])
    status, created = api.dispatch(
        "POST",
        "/v1/radio/presets",
        {
            "profile_key": "weather_band",
            "label": "Local NOAA",
            "frequency_hz": 162550000,
            "owner": "driver",
        },
    )
    assert status == 201
    status, response = api.dispatch("GET", "/v1/radio/presets?profile_key=weather_band")
    assert status == 200
    assert len(response["presets"]) == 8
    assert created["preset"]["id"] in {p["id"] for p in response["presets"]}
    status, response = api.dispatch("GET", "/v1/radio/presets?owner=driver")
    assert status == 200
    assert len(response["presets"]) == 1
