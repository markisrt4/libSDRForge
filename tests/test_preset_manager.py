# SPDX-License-Identifier: MIT
"""Hardware-free multi-owner preset storage tests."""
import json
from pathlib import Path

import pytest

from sdrforge.adapters.json_preset_repository import JsonPresetRepositoryAdapter
from sdrforge.controllers.preset_manager import PresetManager


def test_owner_isolation_and_reload(tmp_path: Path) -> None:
    repo = JsonPresetRepositoryAdapter(tmp_path)
    manager = PresetManager(repo)
    first = manager.add_collection("alice", "Favorites")
    preset = manager.add_preset("alice", first.id, "WOMC", 104_300_000, "WFM", 200_000)
    assert manager.list_presets("bob") == []
    assert manager.list_collections("bob") == []
    assert PresetManager(JsonPresetRepositoryAdapter(tmp_path)).list_presets("alice") == [preset]
    assert manager.delete_preset("bob", preset.id) is False
    assert manager.delete_preset("alice", preset.id) is True


def test_safe_owner_filename_and_atomic_write(tmp_path: Path) -> None:
    repo = JsonPresetRepositoryAdapter(tmp_path)
    manager = PresetManager(repo)
    manager.add_collection("../../someone", "Stations")
    paths = list(tmp_path.glob("*.json"))
    assert len(paths) == 1
    assert paths[0].parent == tmp_path
    assert json.loads(paths[0].read_text())["version"] == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_missing_collection_rejected(tmp_path: Path) -> None:
    manager = PresetManager(JsonPresetRepositoryAdapter(tmp_path))
    with pytest.raises(KeyError):
        manager.add_preset("alice", "missing", "Test", 100_000_000, "WFM", 200_000)


def test_empty_owner_rejected(tmp_path: Path) -> None:
    manager = PresetManager(JsonPresetRepositoryAdapter(tmp_path))
    with pytest.raises(ValueError):
        manager.list_presets("")


def test_update_preset_preserves_identity_and_owner_isolation(tmp_path: Path) -> None:
    manager = PresetManager(JsonPresetRepositoryAdapter(tmp_path))
    favorites = manager.add_collection("alice", "Favorites")
    other = manager.add_collection("alice", "Other")
    original = manager.add_preset("alice", favorites.id, "Old", 104_300_000, "WFM", 200_000)
    with pytest.raises(KeyError):
        manager.update_preset("bob", original.id, name="Hijacked")
    updated = manager.update_preset(
        "alice", original.id, name="New", frequency_hz=101_700_000,
        collection_id=other.id,
    )
    assert updated.id == original.id
    assert updated.name == "New"
    assert updated.frequency_hz == 101_700_000
    assert manager.list_presets("alice", other.id) == [updated]
    assert manager.list_presets("alice", favorites.id) == []


def test_update_rejects_invalid_settings_and_foreign_collection(tmp_path: Path) -> None:
    manager = PresetManager(JsonPresetRepositoryAdapter(tmp_path))
    collection = manager.add_collection("alice", "Favorites")
    foreign = manager.add_collection("bob", "Private")
    preset = manager.add_preset("alice", collection.id, "FM", 104_300_000, "WFM", 200_000)
    with pytest.raises(KeyError):
        manager.update_preset("alice", preset.id, collection_id=foreign.id)
    with pytest.raises(ValueError):
        manager.update_preset("alice", preset.id, frequency_hz=-1)
    assert manager.list_presets("alice") == [preset]


def test_rename_collection_and_safe_delete(tmp_path: Path) -> None:
    manager = PresetManager(JsonPresetRepositoryAdapter(tmp_path))
    collection = manager.add_collection("alice", "Original")
    preset = manager.add_preset("alice", collection.id, "Station", 104_300_000, "WFM", 200_000)
    renamed = manager.rename_collection("alice", collection.id, "Favorites")
    assert renamed.id == collection.id
    assert renamed.name == "Favorites"
    with pytest.raises(ValueError):
        manager.delete_collection("alice", collection.id)
    assert manager.list_presets("alice") == [preset]
    assert manager.delete_collection("bob", collection.id) is False
    assert manager.delete_collection("alice", collection.id, delete_presets=True) is True
    assert manager.list_presets("alice") == []
    assert manager.list_collections("alice") == []


def test_empty_collection_can_be_deleted(tmp_path: Path) -> None:
    manager = PresetManager(JsonPresetRepositoryAdapter(tmp_path))
    collection = manager.add_collection("alice", "Empty")
    assert manager.delete_collection("alice", collection.id)
    assert not manager.delete_collection("alice", collection.id)
