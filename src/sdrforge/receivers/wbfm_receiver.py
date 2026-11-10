# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Compose raw RF IQ downconversion with a channelized WFM decoder."""

from __future__ import annotations

from typing import Literal

import numpy as np

from sdrforge.dsp.digital_downconverter import DigitalDownconverter
from sdrforge.models.iq import IqBlock
from sdrforge.protocols.rds.receiver_controller import RdsReceiverStatus
from sdrforge.receivers.channelized_stereo_wbfm_demodulator import (
    ChannelizedStereoWbfmDemodulator,
)
from sdrforge.receivers.channelized_wbfm_demodulator import ChannelizedWbfmDemodulator


class WbfmReceiver:
    """Decode 2.4 MSPS interleaved U8 RF IQ into 48 kHz mono or stereo PCM.

    One receiver owns one downconverter and one demodulator. Multiple
    receivers can process the same input block for independent channels.
    """

    def __init__(self, *, channel_frequency_hz: int,
                 mode: Literal["mono", "stereo"] = "stereo",
                 rds_enabled: bool = False) -> None:
        if mode not in ("mono", "stereo"):
            raise ValueError("mode must be mono or stereo")
        if rds_enabled and mode != "stereo":
            raise ValueError("RDS requires stereo mode")
        self.channel_frequency_hz = channel_frequency_hz
        self._downconverter = DigitalDownconverter()
        self._demodulator: ChannelizedWbfmDemodulator | ChannelizedStereoWbfmDemodulator
        if mode == "stereo":
            self._demodulator = ChannelizedStereoWbfmDemodulator(
                rds_enabled=rds_enabled
            )
        else:
            self._demodulator = ChannelizedWbfmDemodulator()
        self._last_center_hz: int | None = None

    @property
    def stereo_locked(self) -> bool:
        """Whether the stereo pilot is currently locked."""
        return (self._demodulator.stereo_locked
                if isinstance(self._demodulator, ChannelizedStereoWbfmDemodulator)
                else False)

    @property
    def stereo_blend(self) -> float:
        """Stereo blend amount; zero for mono receivers."""
        return (self._demodulator.stereo_blend
                if isinstance(self._demodulator, ChannelizedStereoWbfmDemodulator)
                else 0.0)

    @property
    def rds_status(self) -> RdsReceiverStatus | None:
        if isinstance(self._demodulator, ChannelizedStereoWbfmDemodulator):
            return self._demodulator.rds_status
        return None

    def reset(self, *, preserve_metadata: bool = False) -> None:
        self._downconverter.reset()
        if isinstance(self._demodulator, ChannelizedStereoWbfmDemodulator):
            self._demodulator.reset(preserve_metadata=preserve_metadata)
        else:
            self._demodulator.reset()
        self._last_center_hz = None

    def process(self, block: IqBlock) -> np.ndarray:
        if (self._last_center_hz is not None
                and self._last_center_hz != block.center_frequency_hz):
            self.reset()
        channel_iq = self._downconverter.process(
            block, self.channel_frequency_hz
        )
        self._last_center_hz = block.center_frequency_hz
        return self._demodulator.process(channel_iq)
