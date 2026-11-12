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
