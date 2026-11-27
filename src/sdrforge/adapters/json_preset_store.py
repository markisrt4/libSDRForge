# SPDX-License-Identifier: MIT
"""!
@brief Atomic JSON persistence for SDRForge-owned user presets.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from threading import RLock

from sdrforge.interfaces.radio_catalog_if import RadioMode, RadioPreset


class JsonPresetStore:
    """!
    @brief Persist user presets independently of the installed SDRForge package.
    """

    def __init__(self, path: Path) -> None:
        """!
        @brief Initialize atomic JSON storage.
        @param self The current instance.
        @param path Writable preset JSON path.
        """
        self._path = Path(path).expanduser()
        self._lock = RLock()

    def _read(self) -> dict[str, RadioPreset]:
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("unsupported preset store schema")
        result = {}
        for item in raw.get("presets", []):
            mode = RadioMode(**item["mode"])
            preset = RadioPreset(**{**item, "mode": mode})
            if preset.id in result:
                raise ValueError("duplicate preset id in store")
            result[preset.id] = preset
        return result

    def _write(self, presets: dict[str, RadioPreset]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(
                {
                    "schema_version": 1,
                    "presets": [asdict(p) for p in presets.values()],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=".presets-",
                delete=False,
            ) as stream:
                name = stream.name
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self._path)
        finally:
            if name is not None and os.path.exists(name):
                os.unlink(name)

    def list_presets(
        self, *, profile_key: str | None = None, owner: str | None = None
    ) -> tuple[RadioPreset, ...]:
        """!
        @brief List stored presets matching optional filters.
        @param self The current instance.
        @param profile_key Optional band profile key.
        @param owner Optional preset owner.
        @return Matching presets.
        """
        with self._lock:
            return tuple(
                p
                for p in self._read().values()
                if (profile_key is None or p.profile_key == profile_key)
                and (owner is None or p.owner == owner)
            )

    def add_preset(self, preset: RadioPreset) -> RadioPreset:
        """!
        @brief Persist a new user preset.
        @param self The current instance.
        @param preset New user preset.
        @return Stored preset.
        """
        with self._lock:
            data = self._read()
            if preset.id in data:
                raise ValueError("preset id already exists")
            if preset.origin != "user":
                raise ValueError("only user presets may be persisted")
            data[preset.id] = preset
            self._write(data)
            return preset

    def update_preset(self, preset: RadioPreset) -> RadioPreset:
        """!
        @brief Replace an existing preset belonging to its owner.
        @param self The current instance.
        @param preset Updated user preset.
        @return Stored replacement.
        """
        with self._lock:
            data = self._read()
            previous = data.get(preset.id)
            if previous is None or previous.owner != preset.owner:
                raise ValueError("preset not found for owner")
            if preset.origin != "user":
                raise ValueError("only user presets may be persisted")
            data[preset.id] = preset
            self._write(data)
            return preset

    def delete_preset(self, preset_id: str, *, owner: str) -> bool:
        """!
        @brief Remove a preset belonging to the specified owner.
        @param self The current instance.
        @param preset_id Preset identifier.
        @param owner Preset owner.
        @return True if a preset was removed.
        """
        with self._lock:
            data = self._read()
            preset = data.get(preset_id)
            if preset is None or preset.owner != owner:
                return False
            del data[preset_id]
            self._write(data)
            return True
