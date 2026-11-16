# SPDX-License-Identifier: MIT
"""!
@brief Portable radio preset model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class RadioPreset:
    """!
    @brief Provide radio preset behavior.
    """
    id: str
    collection_id: str
    name: str
    frequency_hz: int
    modulation: str
    bandwidth_hz: int
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """!
        @brief Validate and normalize the initialized instance.

        @param self The current instance.
        """
        UUID(self.id)
        UUID(self.collection_id)
        if not self.name.strip() or self.frequency_hz <= 0 or self.bandwidth_hz < 0:
            raise ValueError("invalid preset")
        if self.modulation not in {"AM", "FM", "NFM", "WFM"}:
            raise ValueError("unsupported modulation")
