# SPDX-License-Identifier: MIT
"""Owner-scoped preset and collection operations."""
from __future__ import annotations

from dataclasses import replace
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

    def update_preset(
        self, owner_id: str, preset_id: str, *,
        name: str | None = None, frequency_hz: int | None = None,
        modulation: str | None = None, bandwidth_hz: int | None = None,
        collection_id: str | None = None,
    ) -> RadioPreset:
        collections, presets = self.repository.load(owner_id)
        for index, existing in enumerate(presets):
            if existing.id != preset_id:
                continue
            target_collection = collection_id if collection_id is not None else existing.collection_id
            if not any(item.id == target_collection for item in collections):
                raise KeyError("collection not found")
            updated = replace(
                existing,
                name=existing.name if name is None else name,
                frequency_hz=existing.frequency_hz if frequency_hz is None else frequency_hz,
                modulation=existing.modulation if modulation is None else modulation,
                bandwidth_hz=existing.bandwidth_hz if bandwidth_hz is None else bandwidth_hz,
                collection_id=target_collection,
            )
            presets[index] = updated
            self.repository.save(owner_id, collections, presets)
            return updated
        raise KeyError("preset not found")

    def rename_collection(self, owner_id: str, collection_id: str, name: str) -> PresetCollection:
        collections, presets = self.repository.load(owner_id)
        for index, existing in enumerate(collections):
            if existing.id == collection_id:
                updated = replace(existing, name=name)
                collections[index] = updated
                self.repository.save(owner_id, collections, presets)
                return updated
        raise KeyError("collection not found")

    def delete_collection(
        self, owner_id: str, collection_id: str, *, delete_presets: bool = False,
    ) -> bool:
        collections, presets = self.repository.load(owner_id)
        if not any(item.id == collection_id for item in collections):
            return False
        if not delete_presets and any(item.collection_id == collection_id for item in presets):
            raise ValueError("collection contains presets; set delete_presets=True to delete them")
        self.repository.save(
            owner_id,
            [item for item in collections if item.id != collection_id],
            [item for item in presets if item.collection_id != collection_id],
        )
        return True
