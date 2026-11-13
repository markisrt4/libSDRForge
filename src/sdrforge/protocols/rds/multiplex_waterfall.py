# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Small terminal FM multiplex waterfall, with a 57 kHz RDS marker."""

from __future__ import annotations

from collections import deque

import numpy as np


class MultiplexWaterfall:
    """Bounded waterfall; compute FFT only when explicitly updated."""

    def __init__(self, width: int = 56, history: int = 48) -> None:
        if width < 8 or history < 1:
            raise ValueError("invalid waterfall dimensions")
        self.width = width
        self.rows: deque[tuple[int, ...]] = deque(maxlen=history)

    @property
    def rds_column(self) -> int:
        return round(57_000 / 80_000 * (self.width - 1))

    def update(self, samples: np.ndarray) -> None:
        values = np.asarray(samples, dtype=np.float64)
        if len(values) < 256:
            return
        size = min(2048, len(values))
        window = values[-size:] * np.hanning(size)
        spectrum = np.abs(np.fft.rfft(window))
        frequencies = np.fft.rfftfreq(size, 1 / 240_000)
        bins = np.linspace(0, 80_000, self.width)
        powers = np.interp(bins, frequencies, spectrum)
        db = 20 * np.log10(np.maximum(powers, 1e-10))
        floor = float(np.percentile(db, 25))
        levels = np.clip(((db - floor - 3) / 4).astype(int), 0, 7)
        self.rows.append(tuple(int(value) for value in levels))

    def render_cells(self, width: int | None = None) -> list[list[tuple[str, bool]]]:
        """Return glyphs and RDS-column flags for terminal color rendering.

        The RDS flag marks frequency only; it does not claim valid decoding.
        """
        palette = " .:-=+*#"
        limit = self.width if width is None else max(0, min(width, self.width))
        marker = self.rds_column
        return [[(palette[value], index == marker) for index, value in enumerate(row[:limit])]
                for row in self.rows]

    def render_intensity(self, width: int | None = None) -> list[list[int]]:
        """Return oldest-first power levels for a color-aware terminal renderer."""
        limit = self.width if width is None else max(0, min(width, self.width))
        return [list(row[:limit]) for row in self.rows]

    def render(self, width: int | None = None) -> list[str]:
        """Render oldest first; use ASCII for portable Termux terminals."""
        palette = " .:-=+*#"
        limit = self.width if width is None else max(0, min(width, self.width))
        return ["".join(palette[value] for value in row[:limit])
                for row in self.rows]
