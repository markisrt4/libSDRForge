# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""Stereo WFM pipeline from 240 kSPS channelized complex IQ."""

from __future__ import annotations

import numpy as np

from sdrforge.dsp.fm_multiplex_discriminator import FmMultiplexDiscriminator
from sdrforge.dsp.fm_stereo_decoder import FmStereoDecoder
from sdrforge.protocols.rds.receiver_controller import (
    RdsReceiverController,
    RdsReceiverStatus,
)


class ChannelizedStereoWbfmDemodulator:
    """Independent, resettable stereo path; mono WFM remains unchanged."""

    def __init__(self, *, rds_enabled: bool = False) -> None:
        self._rds = RdsReceiverController() if rds_enabled else None
        self._multiplex = FmMultiplexDiscriminator()
        self._stereo = FmStereoDecoder()

    @property
    def rds_status(self) -> RdsReceiverStatus | None:
        return self._rds.status if self._rds is not None else None

    @property
    def stereo_locked(self) -> bool:
        return self._stereo.stereo_locked

    @property
    def stereo_blend(self) -> float:
        return self._stereo.stereo_blend

    def reset(self, *, preserve_metadata: bool = False) -> None:
        self._multiplex.reset()
        self._stereo.reset()
        if self._rds is not None:
            self._rds.reset(preserve_metadata=preserve_metadata)

    def process(self, iq: np.ndarray) -> np.ndarray:
        multiplex = self._multiplex.process(iq)
        if self._rds is not None:
            self._rds.process_multiplex(multiplex)
        return self._stereo.process(multiplex)
