# SPDX-License-Identifier: MIT
"""Explicit, non-destructive importer for legacy OpenRoadCode radio data."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sdrforge.controllers.radio_catalog import RadioCatalog, validate_mode
from sdrforge.interfaces.radio_catalog_if import RadioMode, RadioPreset, RadioProfile


def _group(key: str) -> str:
    if key == "fm_radio":
        return "FM"
    if key == "weather_band":
        return "WEATHER"
    if key == "airband_am":
        return "AIR"
    if key.startswith("ham_"):
        return "HAM"
    return "SCANNER"


def _mode(raw: dict, fallback: RadioMode | None = None) -> RadioMode:
    if not raw and fallback is not None:
        return fallback
    return RadioMode(str(raw["name"]), int(raw["bandwidth"]),
                     int(raw["step_hz"]))


def _preset_id(source: str, profile_key: str, index: int,
               frequency_hz: int, label: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"sdrforge:orc:{source}:{profile_key}:"
                    f"{index}:{frequency_hz}:{label}"))


@dataclass(frozen=True)
class ImportedRadioData:
    catalog: RadioCatalog
    factory_presets: tuple[RadioPreset, ...]
    user_presets: tuple[RadioPreset, ...]


def import_orc_radio_data(
    radio_root: Path,
    *,
    locale: str | None = None,
    user_presets_path: Path | None = None,
    owner: str = "default",
) -> ImportedRadioData:
    """Read ORC JSON into SDRForge models without modifying any input files.

    Common profiles are overridden by a matching locale profile. Locales are
    opt-in; there is deliberately no implicit Romeo selection.
    """
    root = Path(radio_root)
    selected: dict[str, Path] = {}
    directories = [root / "common"]
    if locale is not None:
        if not locale or Path(locale).name != locale or locale in {".", ".."}:
            raise ValueError("locale must be a single directory name")
        directories.append(root / locale)
    for directory in directories:
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                selected[path.stem] = path
    profiles: list[RadioProfile] = []
    factory: list[RadioPreset] = []
    for key, path in sorted(selected.items()):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw["key"] != key:
            raise ValueError(f"profile key does not match filename: {path}")
        mode = _mode(raw["default_mode"])
        band = raw["range"]
        profile = RadioProfile(
            key, str(raw["label"]), _group(key),
            int(band["min_frequency_hz"]), int(band["max_frequency_hz"]),
            int(band["start_frequency_hz"]), mode,
        )
        profiles.append(profile)
        for index, entry in enumerate(raw.get("presets", [])):
            preset_mode = _mode(entry.get("mode") or {}, mode)
            validate_mode(preset_mode)
            frequency = int(entry["frequency_hz"])
            if not profile.minimum_frequency_hz <= frequency <= profile.maximum_frequency_hz:
                raise ValueError(f"factory preset outside profile range: {path}")
            factory.append(RadioPreset(
                _preset_id("factory", key, index, frequency, str(entry["label"])),
                key, str(entry["label"]), frequency, preset_mode,
                owner="factory", origin="factory",
            ))
    catalog = RadioCatalog(tuple(profiles))
    user: list[RadioPreset] = []
    if user_presets_path is not None and Path(user_presets_path).is_file():
        raw_users = json.loads(Path(user_presets_path).read_text(encoding="utf-8"))
        if not isinstance(raw_users, dict):
            raise ValueError("legacy user presets must be a JSON object")
        for key, entries in sorted(raw_users.items()):
            profile = catalog.profile(key)
            if not isinstance(entries, list):
                raise ValueError(f"user preset entries must be a list: {key}")
            for index, entry in enumerate(entries):
                preset_mode = _mode(entry.get("mode") or {}, profile.default_mode)
                validate_mode(preset_mode)
                frequency = int(entry["frequency_hz"])
                if not profile.minimum_frequency_hz <= frequency <= profile.maximum_frequency_hz:
                    raise ValueError(f"user preset outside profile range: {key}")
                label = str(entry["label"]).strip()
                if not label:
                    raise ValueError("user preset label is required")
                user.append(RadioPreset(
                    _preset_id("user", key, index, frequency, label),
                    key, label, frequency, preset_mode, owner=owner, origin="user",
                ))
    return ImportedRadioData(catalog, tuple(factory), tuple(user))


def persist_imported_user_presets(data: ImportedRadioData, store: object) -> int:
    """Save only missing deterministic IDs; repeated imports do not duplicate."""
    existing = {p.id for p in store.list_presets()}
    imported = 0
    for preset in data.user_presets:
        if preset.id not in existing:
            store.add_preset(preset)
            existing.add(preset.id)
            imported += 1
    return imported
