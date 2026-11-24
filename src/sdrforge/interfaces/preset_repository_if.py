# SPDX-License-Identifier: MIT
"""!
@brief Storage contract for owner-scoped radio presets.
"""

from __future__ import annotations

from typing import Protocol

from sdrforge.models.preset_collection import PresetCollection
from sdrforge.models.radio_preset import RadioPreset


class PresetRepositoryIf(Protocol):
    """!
    @brief Define persistent storage operations for owner-scoped presets.
    """

    def load(self, owner_id: str) -> tuple[list[PresetCollection], list[RadioPreset]]:
        """!
        @brief Load all collections and presets belonging to an owner.

        @param self The current instance.
        @param owner_id The preset owner identifier.
        @return The operation result.
        """
        ...

    def save(
        self,
        owner_id: str,
        collections: list[PresetCollection],
        presets: list[RadioPreset],
    ) -> None:
        """!
        @brief Persist an owner's complete collection and preset state.

        @param self The current instance.
        @param owner_id The preset owner identifier.
        @param collections The ``collections`` value.
        @param presets The ``presets`` value.
        """
        ...
