# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Lightweight multiplex waterfall tests."""

import numpy as np
import pytest

from sdrforge.protocols.rds.multiplex_waterfall import MultiplexWaterfall


def test_rds_tone_peak_near_57khz():
    waterfall = MultiplexWaterfall(width=64)
    samples = np.arange(4096) / 240_000
    waterfall.update(np.sin(2 * np.pi * 57_000 * samples))
    assert len(waterfall.rows) == 1
    assert waterfall.rows[0][waterfall.rds_column] >= 4


def test_history_is_bounded_and_rendered():
    waterfall = MultiplexWaterfall(width=16, history=2)
    samples = np.zeros(2048)
    for _ in range(3):
        waterfall.update(samples)
    assert len(waterfall.render()) == 2
    assert all(len(row) == 16 for row in waterfall.render())


def test_short_blocks_are_ignored():
    waterfall = MultiplexWaterfall()
    waterfall.update(np.zeros(128))
    assert waterfall.render() == []


def test_invalid_dimensions():
    with pytest.raises(ValueError):
        MultiplexWaterfall(width=3)
