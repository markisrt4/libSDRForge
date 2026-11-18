# SPDX-License-Identifier: MIT
"""!
@brief Named collection of user radio presets.
"""
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class PresetCollection:
    """!
    @brief Provide preset collection behavior.
    """
    id: str
    name: str

    def __post_init__(self) -> None:
        """!
        @brief Validate and normalize the initialized instance.

        @param self The current instance.
        """
        UUID(self.id)
        if not self.name.strip():
            raise ValueError("collection name required")
