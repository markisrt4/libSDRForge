# SPDX-License-Identifier: MIT
"""!
@brief Validated, hardware-independent radio profile and preset services.
"""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from sdrforge.interfaces.radio_catalog_if import (
    PresetStoreIf, RadioCatalogIf, RadioMode, RadioPreset, RadioProfile,
)

_SUPPORTED_MODES = frozenset({"FM", "WFM", "NFM", "AM"})


def validate_mode(mode: RadioMode) -> None:
    """!
    @brief Validate supported demodulation, bandwidth and tuning step.
    @param mode Radio mode to validate.
    """
    if mode.name.upper() not in _SUPPORTED_MODES:
        raise ValueError(f"unsupported mode: {mode.name}")
    if type(mode.bandwidth_hz) is not int or mode.bandwidth_hz < 0:
        raise ValueError("bandwidth_hz must be a nonnegative integer")
    if type(mode.step_hz) is not int or mode.step_hz <= 0:
        raise ValueError("step_hz must be a positive integer")


def validate_profile(profile: RadioProfile) -> None:
    """!
    @brief Validate profile identity, frequency range and default mode.
    @param profile Band profile to validate.
    """
    if not profile.key.strip() or not profile.label.strip() or not profile.group.strip():
        raise ValueError("profile key, label, and group are required")
    low, high, start = (profile.minimum_frequency_hz,
                        profile.maximum_frequency_hz, profile.start_frequency_hz)
    if any(type(value) is not int for value in (low, high, start)):
        raise ValueError("profile frequencies must be integer Hz")
    if not 0 < low <= start <= high:
        raise ValueError("invalid profile frequency range")
    validate_mode(profile.default_mode)


class RadioCatalog(RadioCatalogIf):
    """!
    @brief Immutable catalog of installed band profiles.
    """

    def __init__(self, profiles: tuple[RadioProfile, ...]) -> None:
        """!
        @brief Validate and index installed profiles.
        @param self The current instance.
        @param profiles Installed band profiles.
        """
        self._profiles: dict[str, RadioProfile] = {}
        for profile in profiles:
            validate_profile(profile)
            if profile.key in self._profiles:
                raise ValueError(f"duplicate profile key: {profile.key}")
            self._profiles[profile.key] = profile

    def profiles(self) -> tuple[RadioProfile, ...]:
        """!
        @brief Enumerate installed profiles.
        @param self The current instance.
        @return Installed profiles.
        """
        return tuple(self._profiles.values())

    def profile(self, key: str) -> RadioProfile:
        """!
        @brief Look up a profile by key.
        @param self The current instance.
        @param key Unique profile key.
        @return Matching profile.
        """
        try:
            return self._profiles[key]
        except KeyError as exc:
            raise ValueError(f"unknown profile: {key}") from exc


class PresetService:
    """!
    @brief Validate preset mutations against the canonical band catalog.
    """

    def __init__(self, catalog: RadioCatalogIf, store: PresetStoreIf) -> None:
        """!
        @brief Bind catalog validation to preset persistence.
        @param self The current instance.
        @param catalog Canonical band catalog.
        @param store Writable preset store.
        """
        self._catalog = catalog
        self._store = store

    def list_presets(self, *, profile_key: str | None = None,
                     owner: str | None = None) -> tuple[RadioPreset, ...]:
        """!
        @brief List presets matching optional filters.
        @param self The current instance.
        @param profile_key Optional band profile key.
        @param owner Optional preset owner.
        @return Matching user presets.
        """
        if profile_key is not None:
            self._catalog.profile(profile_key)
        return self._store.list_presets(profile_key=profile_key, owner=owner)

    def save(self, *, profile_key: str, label: str, frequency_hz: int,
             mode: RadioMode | None = None, owner: str = "default") -> RadioPreset:
        """!
        @brief Validate and create a user preset.
        @param self The current instance.
        @param profile_key Band profile key.
        @param label Display label.
        @param frequency_hz Listening frequency in hertz.
        @param mode Optional mode overriding the profile default.
        @param owner Preset owner.
        @return Newly stored preset.
        """
        profile = self._catalog.profile(profile_key)
        actual_mode = mode or profile.default_mode
        self._validate(profile, label, frequency_hz, actual_mode, owner)
        preset = RadioPreset(str(uuid4()), profile_key, label.strip(),
                             frequency_hz, actual_mode, owner)
        return self._store.add_preset(preset)

    def update(self, preset: RadioPreset) -> RadioPreset:
        """!
        @brief Validate and replace a user preset.
        @param self The current instance.
        @param preset Updated preset.
        @return Stored replacement.
        """
        if preset.origin != "user":
            raise ValueError("factory and scan findings cannot be edited as user presets")
        profile = self._catalog.profile(preset.profile_key)
        self._validate(profile, preset.label, preset.frequency_hz,
                       preset.mode, preset.owner)
        return self._store.update_preset(replace(preset, label=preset.label.strip()))

    def delete(self, preset_id: str, *, owner: str) -> bool:
        """!
        @brief Delete a preset for its owner.
        @param self The current instance.
        @param preset_id Preset identifier.
        @param owner Preset owner.
        @return True if removed.
        """
        if not owner.strip():
            raise ValueError("owner is required")
        return self._store.delete_preset(preset_id, owner=owner)

    @staticmethod
    def _validate(profile: RadioProfile, label: str, frequency_hz: int,
                  mode: RadioMode, owner: str) -> None:
        if not label.strip() or not owner.strip():
            raise ValueError("label and owner are required")
        if type(frequency_hz) is not int or not (
            profile.minimum_frequency_hz <= frequency_hz
            <= profile.maximum_frequency_hz
        ):
            raise ValueError("preset frequency outside profile range")
        validate_mode(mode)
