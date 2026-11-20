# SPDX-License-Identifier: MIT
"""Bundled SDRForge factory radio profiles and presets."""
from __future__ import annotations

from importlib.resources import files
import json
from uuid import NAMESPACE_URL, uuid5

from sdrforge.controllers.radio_catalog import RadioCatalog
from sdrforge.interfaces.radio_catalog_if import RadioMode, RadioPreset, RadioProfile


def load_factory_radio_catalog() -> tuple[RadioCatalog, tuple[RadioPreset, ...]]:
    """Load packaged, locale-neutral profiles without requiring ORC."""
    root = files("sdrforge").joinpath("data/radio")
    profiles: list[RadioProfile] = []
    presets: list[RadioPreset] = []
    for resource in sorted(root.iterdir(), key=lambda p: p.name):
        if not resource.name.endswith(".json"):
            continue
        raw = json.loads(resource.read_text(encoding="utf-8"))
        mode = raw["default_mode"]
        default = RadioMode(str(mode["name"]), int(mode["bandwidth"]),
                            int(mode["step_hz"]))
        band = raw["range"]
        profile = RadioProfile(
            str(raw["key"]), str(raw["label"]), str(raw["group"]),
            int(band["min_frequency_hz"]), int(band["max_frequency_hz"]),
            int(band["start_frequency_hz"]), default,
        )
        profiles.append(profile)
        for index, entry in enumerate(raw.get("presets", [])):
            frequency = int(entry["frequency_hz"])
            preset_mode = entry.get("mode") or mode
            presets.append(RadioPreset(
                str(uuid5(NAMESPACE_URL, f"sdrforge:factory:{profile.key}:"
                          f"{index}:{frequency}:{entry['label']}")),
                profile.key, str(entry["label"]), frequency,
                RadioMode(str(preset_mode["name"]), int(preset_mode["bandwidth"]),
                          int(preset_mode["step_hz"])),
                owner="factory", origin="factory",
            ))
    return RadioCatalog(tuple(profiles)), tuple(presets)
