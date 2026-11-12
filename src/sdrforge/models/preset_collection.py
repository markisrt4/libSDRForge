# SPDX-License-Identifier: MIT
"""Named collection of user radio presets."""
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class PresetCollection:
    id: str
    name: str

    def __post_init__(self) -> None:
        UUID(self.id)
        if not self.name.strip():
            raise ValueError("collection name required")
