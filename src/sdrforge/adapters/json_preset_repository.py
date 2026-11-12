# SPDX-License-Identifier: MIT
"""Atomic owner-scoped JSON preset storage."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from sdrforge.models.preset_collection import PresetCollection
from sdrforge.models.radio_preset import RadioPreset


class JsonPresetRepositoryAdapter:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def _path(self, owner_id: str) -> Path:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id required")
        key = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()
        return self.directory / f"{key}.json"

    def load(self, owner_id: str) -> tuple[list[PresetCollection], list[RadioPreset]]:
        path = self._path(owner_id)
        if not path.exists():
            return [], []
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("unsupported preset format")
        return (
            [PresetCollection(**item) for item in data["collections"]],
            [RadioPreset(**item) for item in data["presets"]],
        )

    def save(self, owner_id: str, collections: list[PresetCollection], presets: list[RadioPreset]) -> None:
        path = self._path(owner_id)
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({
            "version": 1,
            "collections": [asdict(item) for item in collections],
            "presets": [asdict(item) for item in presets],
        }, indent=2, sort_keys=True)
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.directory,
                prefix=".presets-", suffix=".tmp", delete=False,
            ) as stream:
                temp_path = stream.name
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path is not None and os.path.exists(temp_path):
                os.unlink(temp_path)
