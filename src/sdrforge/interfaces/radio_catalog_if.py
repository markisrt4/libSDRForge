# SPDX-License-Identifier: MIT
"""!
@brief Hardware-independent radio profile and preset contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RadioMode:
    """!
    @brief Demodulation mode, bandwidth and tuning step.
    """

    name: str
    bandwidth_hz: int
    step_hz: int


@dataclass(frozen=True)
class RadioProfile:
    """!
    @brief Named band profile with frequency limits and default mode.
    """

    key: str
    label: str
    group: str
    minimum_frequency_hz: int
    maximum_frequency_hz: int
    start_frequency_hz: int
    default_mode: RadioMode


@dataclass(frozen=True)
class RadioPreset:
    """!
    @brief Named frequency and mode associated with a profile and owner.
    """

    id: str
    profile_key: str
    label: str
    frequency_hz: int
    mode: RadioMode
    owner: str = "default"
    origin: str = "user"


class RadioCatalogIf(Protocol):
    """!
    @brief Profile lookup without knowledge of hardware or storage.
    """

    def profiles(self) -> tuple[RadioProfile, ...]:
        """!
        @brief Enumerate installed profiles.
        @param self The current instance.
        @return Installed profiles.
        """
        ...

    def profile(self, key: str) -> RadioProfile:
        """!
        @brief Look up a profile by key.
        @param self The current instance.
        @param key Unique profile key.
        @return Matching profile.
        """
        ...


class PresetStoreIf(Protocol):
    """!
    @brief Per-owner preset CRUD; immutable factory presets are not writable.
    """

    def list_presets(
        self, *, profile_key: str | None = None, owner: str | None = None
    ) -> tuple[RadioPreset, ...]:
        """!
        @brief List presets matching optional filters.
        @param self The current instance.
        @param profile_key Optional band profile key.
        @param owner Optional preset owner.
        @return Matching presets.
        """
        ...

    def add_preset(self, preset: RadioPreset) -> RadioPreset:
        """!
        @brief Persist a new user preset.
        @param self The current instance.
        @param preset New preset.
        @return Stored preset.
        """
        ...

    def update_preset(self, preset: RadioPreset) -> RadioPreset:
        """!
        @brief Replace an existing user preset.
        @param self The current instance.
        @param preset Updated preset.
        @return Stored replacement.
        """
        ...

    def delete_preset(self, preset_id: str, *, owner: str) -> bool:
        """!
        @brief Remove a preset belonging to its owner.
        @param self The current instance.
        @param preset_id Preset identifier.
        @param owner Preset owner.
        @return True if removed.
        """
        ...
