# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""!
@brief Hardware-independent mixed-mode virtual SDR receiver.

The physical IQ source is injected by the caller. One IQ block feeds all
channels; each channel owns independent downconversion and demodulation state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol

import numpy as np

from sdrforge.core.virtual_receiver_manager import (
    VirtualChannel,
    VirtualReceiverManager,
)
from sdrforge.diagnostics.channel_rf_telemetry import (
    ChannelRfTelemetry,
    adc_clip_fraction,
    measure_channel_rf,
)
from sdrforge.models.iq import IqBlock
from sdrforge.protocols.rds.receiver_controller import RdsReceiverStatus
from sdrforge.receivers.channelized_am_demodulator import ChannelizedAmDemodulator
from sdrforge.receivers.channelized_nbfm_demodulator import ChannelizedNbfmDemodulator
from sdrforge.receivers.channelized_stereo_wbfm_demodulator import (
    ChannelizedStereoWbfmDemodulator,
)
from sdrforge.receivers.channelized_wbfm_demodulator import ChannelizedWbfmDemodulator


@dataclass(frozen=True)
class RadioChannel:
    """!
    @brief Provide radio channel behavior.
    """
    name: str
    frequency_hz: int
    mode: str
    bandwidth_hz: int | None = None


class _ChannelDemodulator(Protocol):
    def reset(self) -> None: ...

    def process(self, iq: np.ndarray) -> np.ndarray: ...


class MultiModeRadioReceiver:
    """!
    @brief Demodulate independently tuned AM/NFM/WFM channels from shared IQ.
    """

    _BANDWIDTHS: ClassVar[dict[str, int]] = {"WFM": 180_000, "NFM": 25_000, "AM": 25_000}
    _DEMODULATORS: ClassVar[dict[str, type[_ChannelDemodulator]]] = {
        "WFM": ChannelizedWbfmDemodulator,
        "NFM": ChannelizedNbfmDemodulator,
        "AM": ChannelizedAmDemodulator,
    }

    def __init__(self, *, input_rate_hz: int = 2_400_000,
                 stereo_wfm: bool = False, rds_wfm: bool = False) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param input_rate_hz The ``input_rate_hz`` value.
        @param stereo_wfm The ``stereo_wfm`` value.
        @param rds_wfm The ``rds_wfm`` value.
        """
        if rds_wfm and not stereo_wfm:
            raise ValueError("rds_wfm requires stereo_wfm multiplex pipeline")
        self._manager = VirtualReceiverManager(input_rate_hz=input_rate_hz)
        self._stereo_wfm = stereo_wfm
        self._rds_wfm = rds_wfm
        self._decoders: dict[str, _ChannelDemodulator] = {}
        self._configs: dict[str, RadioChannel] = {}
        self._telemetry: dict[str, ChannelRfTelemetry] = {}

    @property
    def telemetry(self) -> dict[str, ChannelRfTelemetry]:
        """!
        @brief Return the telemetry.

        @param self The current instance.
        @return The operation result.
        """
        return dict(self._telemetry)

    @property
    def rds_status(self) -> dict[str, RdsReceiverStatus]:
        """!
        @brief Return the rds status.

        @param self The current instance.
        @return The operation result.
        """
        return {name: decoder.rds_status for name, decoder in self._decoders.items()
                if isinstance(decoder, ChannelizedStereoWbfmDemodulator)
                and decoder.rds_status is not None}

    @property
    def channels(self) -> tuple[RadioChannel, ...]:
        """!
        @brief Return the channels.

        @param self The current instance.
        @return The operation result.
        """
        return tuple(self._configs.values())

    def add_channel(self, config: RadioChannel) -> None:
        """!
        @brief Add channel.

        @param self The current instance.
        @param config The ``config`` value.
        """
        mode = config.mode.upper()
        if mode not in self._DEMODULATORS:
            raise ValueError(f"unsupported radio mode: {config.mode}")
        bandwidth = (self._BANDWIDTHS[mode]
                     if config.bandwidth_hz is None else config.bandwidth_hz)
        if mode == "WFM" and bandwidth < 150_000:
            raise ValueError("WFM channel bandwidth must be at least 150 kHz")
        channel = VirtualChannel(config.name, config.frequency_hz,
                                 bandwidth_hz=bandwidth, output_rate_hz=240_000)
        self._manager.add_channel(channel)
        self._configs[config.name] = RadioChannel(config.name, config.frequency_hz,
                                                   mode, bandwidth)
        decoder_type = (ChannelizedStereoWbfmDemodulator
                        if mode == "WFM" and self._stereo_wfm
                        else self._DEMODULATORS[mode])
        self._decoders[config.name] = (decoder_type(rds_enabled=self._rds_wfm)
                                       if decoder_type is ChannelizedStereoWbfmDemodulator
                                       else decoder_type())

    def remove_channel(self, name: str) -> None:
        """!
        @brief Remove channel.

        @param self The current instance.
        @param name The ``name`` value.
        """
        self._manager.remove_channel(name)
        del self._decoders[name]
        del self._configs[name]
        self._telemetry.pop(name, None)

    def retune_channel(self, name: str, frequency_hz: int) -> None:
        """!
        @brief Retune channel.

        @param self The current instance.
        @param name The ``name`` value.
        @param frequency_hz The frequency in hertz.
        """
        self._manager.retune_channel(name, frequency_hz)
        old = self._configs[name]
        self._configs[name] = RadioChannel(old.name, frequency_hz, old.mode,
                                            old.bandwidth_hz)
        self._decoders[name].reset()
        self._telemetry.pop(name, None)

    def reset(self, *, preserve_metadata: bool = False) -> None:
        """!
        @brief Reset DSP state; optionally retain published RDS station metadata.

        @param self The current instance.
        @param preserve_metadata The ``preserve_metadata`` value.
        """
        self._manager.reset()
        self._telemetry.clear()
        for decoder in self._decoders.values():
            if isinstance(decoder, ChannelizedStereoWbfmDemodulator):
                decoder.reset(preserve_metadata=preserve_metadata)
            else:
                decoder.reset()

    def process(self, block: IqBlock) -> dict[str, np.ndarray]:
        """!
        @brief Return 48 kHz float32 PCM; stereo WFM yields (frames, 2).

        @param self The current instance.
        @param block The IQ sample block to process.
        @return The operation result.
        """
        iq_by_channel = self._manager.process(block)
        clipping = adc_clip_fraction(block.samples)
        self._telemetry = {
            name: measure_channel_rf(samples, adc_clip_fraction=clipping)
            for name, samples in iq_by_channel.items()
        }
        return {
            name: self._decoders[name].process(samples)
            for name, samples in iq_by_channel.items()
        }
