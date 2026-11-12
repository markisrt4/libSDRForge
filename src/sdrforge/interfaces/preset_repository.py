# SPDX-License-Identifier: MIT
"""Storage contract for owner-scoped radio presets."""
from __future__ import annotations

from typing import Protocol

from sdrforge.models.preset_collection import PresetCollection
from sdrforge.models.radio_preset import RadioPreset


class PresetRepositoryIf(Protocol):
    def load(self, owner_id: str) -> tuple[list[PresetCollection], list[RadioPreset]]: ...
    def save(self, owner_id: str, collections: list[PresetCollection], presets: list[RadioPreset]) -> None: ...
