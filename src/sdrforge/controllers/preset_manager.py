# SPDX-License-Identifier: MIT
"""Owner-scoped preset and collection operations."""
from __future__ import annotations

from uuid import uuid4

from sdrforge.interfaces.preset_repository import PresetRepositoryIf
from sdrforge.models.preset_collection import PresetCollection
from sdrforge.models.radio_preset import RadioPreset


class PresetManager:
    def __init__(self, repository: PresetRepositoryIf) -> None:
        self.repository = repository

    def list_collections(self, owner_id: str) -> list[PresetCollection]:
        return self.repository.load(owner_id)[0]

    def list_presets(self, owner_id: str, collection_id: str | None = None) -> list[RadioPreset]:
        presets = self.repository.load(owner_id)[1]
        return [p for p in presets if p.collection_id == collection_id] if collection_id else presets

    def add_collection(self, owner_id: str, name: str) -> PresetCollection:
        collections, presets = self.repository.load(owner_id)
        collection = PresetCollection(str(uuid4()), name)
        self.repository.save(owner_id, [*collections, collection], presets)
        return collection

    def add_preset(
        self, owner_id: str, collection_id: str, name: str,
        frequency_hz: int, modulation: str, bandwidth_hz: int,
    ) -> RadioPreset:
        collections, presets = self.repository.load(owner_id)
        if not any(c.id == collection_id for c in collections):
            raise KeyError("collection not found")
        preset = RadioPreset(str(uuid4()), collection_id, name, frequency_hz, modulation, bandwidth_hz)
        self.repository.save(owner_id, collections, [*presets, preset])
        return preset

    def delete_preset(self, owner_id: str, preset_id: str) -> bool:
        collections, presets = self.repository.load(owner_id)
        remaining = [p for p in presets if p.id != preset_id]
        if len(remaining) == len(presets):
            return False
        self.repository.save(owner_id, collections, remaining)
        return True
