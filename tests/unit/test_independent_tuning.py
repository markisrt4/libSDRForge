# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Regression coverage for independent RF and listening frequencies."""

from unittest.mock import Mock

import pytest

from sdrforge.models.iq import IqBlock
from sdrforge.session import RadioSession


@pytest.mark.parametrize("mode, bandwidth", [("WFM", 200_000), ("AM", 6_000), ("NFM", 7_500)])
def test_in_band_tuning_preserves_acquisition(mode: str, bandwidth: int) -> None:
    source = Mock()
    observer = Mock()
    source.get_acquisition_stats.return_value = {"dropped_blocks": 0}
    session = RadioSession(
        frequency_hz=94_700_000,
        source=source,
        rf_warmup_seconds=0,
        iq_observer=observer,
    )
    session.set_demodulation(mode, bandwidth)
    session.start()
    try:
        session.retune(95_100_000)
        source.set_center_frequency.assert_called_once_with(94_700_000)
        assert session.frequency_hz == 95_100_000
        assert session.acquisition_frequency_hz == 94_700_000
        assert session.channel_bandwidth_hz == bandwidth
        assert session.receiver.channel_frequency_hz == 95_100_000
        block = IqBlock(bytes([128, 128]) * 5000, 94_700_000, 2_400_000, 0)
        source.read_iq.return_value = block
        session.read()
        observer.assert_called_once_with(block)
        session.retune(104_300_000)
        assert session.acquisition_frequency_hz == 104_300_000
        source.set_center_frequency.assert_called_with(104_300_000)
    finally:
        session.stop()


def test_mode_change_rechecks_channel_width() -> None:
    source = Mock()
    session = RadioSession(
        frequency_hz=94_700_000, source=source, rf_warmup_seconds=0
    )
    session.set_demodulation("NFM", 7_500)
    session.start()
    try:
        session.retune(95_850_000)
        source.set_center_frequency.assert_called_once_with(94_700_000)
        session.set_demodulation("WFM", 200_000)
        source.set_center_frequency.assert_called_with(95_850_000)
        assert session.acquisition_frequency_hz == 95_850_000
    finally:
        session.stop()
