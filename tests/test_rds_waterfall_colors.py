# SPDX-License-Identifier: MIT
"""Hardware-free waterfall marker tests."""

import numpy as np

from sdrforge.protocols.rds.multiplex_waterfall import MultiplexWaterfall


def test_rds_marker_tracks_57khz_bin():
    waterfall = MultiplexWaterfall(width=56, history=2)
    samples = np.sin(2 * np.pi * 57_000 * np.arange(4096) / 240_000)
    waterfall.update(samples)
    cells = waterfall.render_cells()
    assert len(cells) == 1
    assert len(cells[0]) == 56
    marked = [index for index, (_, is_rds) in enumerate(cells[0]) if is_rds]
    assert marked == [waterfall.rds_column]
    assert waterfall.render() == ["".join(glyph for glyph, _ in cells[0])]


def test_narrow_waterfall_does_not_mark_hidden_rds_column():
    waterfall = MultiplexWaterfall(width=56)
    waterfall.update(np.zeros(2048))
    assert not any(is_rds for _, is_rds in waterfall.render_cells(width=12)[0])
    assert len(waterfall.render_cells(width=12)[0]) == 12
