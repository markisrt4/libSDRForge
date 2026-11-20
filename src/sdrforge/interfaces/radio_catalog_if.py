# SPDX-License-Identifier: MIT
"""Hardware-independent radio profile and preset contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RadioMode:
    name: str
    bandwidth_hz: int
    step_hz: int


@dataclass(frozen=True)
class RadioProfile:
    key: str
    label: str
    group: str
    minimum_frequency_hz: int
    maximum_frequency_hz: int
    start_frequency_hz: int
    default_mode: RadioMode


@dataclass(frozen=True)
class RadioPreset:
    id: str
    profile_key: str
    label: str
    frequency_hz: int
    mode: RadioMode
    owner: str = "default"
    origin: str = "user"


class RadioCatalogIf(Protocol):
    """Profile lookup without knowledge of hardware or storage."""

    def profiles(self) -> tuple[RadioProfile, ...]: ...

    def profile(self, key: str) -> RadioProfile: ...


class PresetStoreIf(Protocol):
    """Per-owner preset CRUD; immutable factory presets are not writable."""

    def list_presets(self, *, profile_key: str | None = None,
                     owner: str | None = None) -> tuple[RadioPreset, ...]: ...

    def add_preset(self, preset: RadioPreset) -> RadioPreset: ...

    def update_preset(self, preset: RadioPreset) -> RadioPreset: ...

    def delete_preset(self, preset_id: str, *, owner: str) -> bool: ...
