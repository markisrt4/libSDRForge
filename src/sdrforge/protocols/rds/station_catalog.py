# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Persistent station identity observations with explicit trust provenance."""

from __future__ import annotations

import json
from pathlib import Path


class StationCatalog:
    """Store verified and experimental station observations separately.

    Experimental observations are never promoted to verified automatically.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._stations: dict[str, dict[str, object]] = {}
        if self.path.exists():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("version") != 1 or not isinstance(payload.get("stations"), dict):
                raise ValueError("unsupported station catalog format")
            self._stations = payload["stations"]

    @property
    def stations(self) -> dict[str, dict[str, object]]:
        return {key: dict(value) for key, value in self._stations.items()}

    def observe(self, *, frequency_hz: int, pi: int, verified: bool,
                program_service: str | None = None) -> None:
        if not 0 <= pi <= 0xFFFF or frequency_hz <= 0:
            raise ValueError("invalid station identity")
        key = f"{frequency_hz}:{pi:04X}"
        entry = self._stations.setdefault(key, {
            "frequency_hz": frequency_hz, "pi": f"0x{pi:04X}",
            "verified": False, "observations": 0, "experimental_observations": 0,
            "program_service": None,
        })
        counter = "observations" if verified else "experimental_observations"
        previous = entry[counter]
        if not isinstance(previous, int):
            raise TypeError("invalid station observation counter")
        entry[counter] = previous + 1
        if verified:
            entry["verified"] = True
            if program_service and program_service.strip():
                entry["program_service"] = program_service.strip()

    def observe_scan(self, *, frequency_hz: int, modulation: str,
                     signal_db: float, noise_db: float) -> None:
        """Persist an RF-discovered frequency without inventing an RDS PI."""
        if frequency_hz <= 0:
            raise ValueError("invalid frequency")
        key = f"{frequency_hz}:RF"
        entry = self._stations.setdefault(key, {
            "frequency_hz": frequency_hz, "pi": None, "verified": False,
            "observations": 0, "experimental_observations": 0,
            "program_service": None,
        })
        previous = entry.get("scan_observations", 0)
        if not isinstance(previous, int):
            raise TypeError("invalid scan observation counter")
        entry.update(modulation=modulation, signal_db=signal_db,
                     noise_db=noise_db, scan_observations=previous + 1)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".new")
        temp.write_text(json.dumps({"version": 1, "stations": self._stations},
                                   indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.path)
