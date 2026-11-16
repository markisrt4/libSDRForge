# SPDX-License-Identifier: MIT
"""Storage contract for owner-scoped radio presets."""
from __future__ import annotations

from typing import Protocol

from sdrforge.models.preset_collection import PresetCollection
from sdrforge.models.radio_preset import RadioPreset


class PresetRepositoryIf(Protocol):
    """Define persistent storage operations for owner-scoped presets."""

    def load(self, owner_id: str) -> tuple[list[PresetCollection], list[RadioPreset]]:
        """Load all collections and presets belonging to an owner."""
        ...

    def save(self, owner_id: str, collections: list[PresetCollection], presets: list[RadioPreset]) -> None:
        """Persist an owner's complete collection and preset state."""
        ...
