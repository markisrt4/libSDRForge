# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT
"""!
@brief Stereo WFM pipeline from 240 kSPS channelized complex IQ.
"""

from __future__ import annotations

import numpy as np

from sdrforge.dsp.fm_multiplex_discriminator import FmMultiplexDiscriminator
from sdrforge.dsp.fm_stereo_decoder import FmStereoDecoder
from sdrforge.protocols.rds.rds_block_sync import RdsGroup
from sdrforge.protocols.rds.rds_soft_confirmation import ExperimentalRadioText
from sdrforge.protocols.rds.receiver_controller import (
    RdsReceiverController,
    RdsReceiverStatus,
)


class ChannelizedStereoWbfmDemodulator:
    """!
    @brief Independent, resettable stereo path; mono WFM remains unchanged.
    """

    def __init__(self, *, rds_enabled: bool = False,
                 rds_persistent_sync: bool = False,
                 rds_experimental_soft_pairs: bool = False,
                 rds_extractor_cutoff_hz: float = 3_000.0) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param rds_enabled The ``rds_enabled`` value.
        @param rds_persistent_sync The ``rds_persistent_sync`` value.
        @param rds_experimental_soft_pairs The ``rds_experimental_soft_pairs`` value.
        @param rds_extractor_cutoff_hz The ``rds_extractor_cutoff_hz`` value.
        """
        self._rds = (RdsReceiverController(persistent_sync=rds_persistent_sync,
                                           experimental_soft_pairs=rds_experimental_soft_pairs,
                                           extractor_cutoff_hz=rds_extractor_cutoff_hz)
                     if rds_enabled else None)
        self._multiplex = FmMultiplexDiscriminator()
        self._stereo = FmStereoDecoder()
        self._last_rds_groups: tuple[RdsGroup, ...] = ()
        self._multiplex_preview = np.empty(0, dtype=np.float32)
        self._last_multiplex = np.empty(0, dtype=np.float32)

    @property
    def rds_status(self) -> RdsReceiverStatus | None:
        """!
        @brief Return the rds status.

        @param self The current instance.
        @return The operation result.
        """
        return self._rds.status if self._rds is not None else None

    @property
    def last_rds_groups(self) -> tuple[RdsGroup, ...]:
        """!
        @brief CRC-validated groups from the most recent process call.

        @param self The current instance.
        @return The operation result.
        """
        return self._last_rds_groups

    @property
    def experimental_rds_groups(self) -> tuple[RdsGroup, ...]:
        """!
        @brief Speculative CRC candidates, never used for trusted metadata.

        @param self The current instance.
        @return The operation result.
        """
        return self._rds.experimental_soft_last_groups if self._rds is not None else ()

    @property
    def experimental_radio_text(self) -> tuple[ExperimentalRadioText, ...]:
        """!
        @brief Provisional per-phase RadioText previews, not trusted metadata.

        @param self The current instance.
        @return The operation result.
        """
        return self._rds.experimental_radio_text if self._rds is not None else ()

    @property
    def multiplex_preview(self) -> np.ndarray:
        """!
        @brief Recent 240 kSPS multiplex samples for optional diagnostics.

        @param self The current instance.
        @return The operation result.
        """
        return self._multiplex_preview

    @property
    def last_multiplex(self) -> np.ndarray:
        """!
        @brief Full 240 kHz multiplex from the most recent processed block.

        @param self The current instance.
        @return The operation result.
        """
        return self._last_multiplex

    @property
    def stereo_locked(self) -> bool:
        """!
        @brief Return the stereo locked.

        @param self The current instance.
        @return The operation result.
        """
        return self._stereo.stereo_locked

    @property
    def stereo_blend(self) -> float:
        """!
        @brief Return the stereo blend.

        @param self The current instance.
        @return The operation result.
        """
        return self._stereo.stereo_blend

    def reset(self, *, preserve_metadata: bool = False) -> None:
        """!
        @brief Reset the component.

        @param self The current instance.
        @param preserve_metadata The ``preserve_metadata`` value.
        """
        self._last_rds_groups = ()
        self._multiplex_preview = np.empty(0, dtype=np.float32)
        self._multiplex.reset()
        self._stereo.reset()
        if self._rds is not None:
            self._rds.reset(preserve_metadata=preserve_metadata)

    def process(self, iq: np.ndarray) -> np.ndarray:
        """!
        @brief Process the component.

        @param self The current instance.
        @param iq The complex IQ samples to process.
        @return The operation result.
        """
        multiplex = self._multiplex.process(iq)
        self._multiplex_preview = multiplex[-4096:]
        self._last_multiplex = multiplex
        if self._rds is not None:
            self._last_rds_groups = tuple(self._rds.process_multiplex(multiplex))
        return self._stereo.process(multiplex)
