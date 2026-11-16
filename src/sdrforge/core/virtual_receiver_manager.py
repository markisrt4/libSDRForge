# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""!
@brief Fan out one captured IQ block to independently tuned virtual receivers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sdrforge.dsp.digital_downconverter import DigitalDownconverter
from sdrforge.models.iq import IqBlock


@dataclass(frozen=True)
class VirtualChannel:
    """!
    @brief Configuration of one independent receive channel.
    """

    name: str
    frequency_hz: int
    bandwidth_hz: int = 180_000
    output_rate_hz: int = 240_000


class VirtualReceiverManager:
    """!
    @brief Channelize shared IQ without opening or retuning physical hardware.

    The caller owns acquisition and supplies each captured block once.
    A separate downconverter instance retains state for each channel.
    """

    def __init__(self, *, input_rate_hz: int = 2_400_000) -> None:
        """!
        @brief Initialize the instance.

        @param self The current instance.
        @param input_rate_hz The ``input_rate_hz`` value.
        """
        if input_rate_hz <= 0:
            raise ValueError("input_rate_hz must be positive")
        self.input_rate_hz = input_rate_hz
        self._channels: dict[str, tuple[VirtualChannel, DigitalDownconverter]] = {}

    @property
    def channels(self) -> tuple[VirtualChannel, ...]:
        """!
        @brief Return the channels.

        @param self The current instance.
        @return The operation result.
        """
        return tuple(config for config, _ in self._channels.values())

    def add_channel(self, config: VirtualChannel) -> None:
        """!
        @brief Add channel.

        @param self The current instance.
        @param config The ``config`` value.
        """
        if not config.name.strip():
            raise ValueError("channel name must not be empty")
        if config.frequency_hz <= 0:
            raise ValueError("channel frequency must be positive")
        if config.name in self._channels:
            raise ValueError(f"channel already exists: {config.name}")
        converter = DigitalDownconverter(
            input_rate_hz=self.input_rate_hz,
            output_rate_hz=config.output_rate_hz,
            channel_bandwidth_hz=config.bandwidth_hz,
        )
        self._channels[config.name] = (config, converter)

    def remove_channel(self, name: str) -> None:
        """!
        @brief Remove channel.

        @param self The current instance.
        @param name The ``name`` value.
        """
        del self._channels[name]

    def retune_channel(self, name: str, frequency_hz: int) -> None:
        """!
        @brief Retune channel.

        @param self The current instance.
        @param name The ``name`` value.
        @param frequency_hz The frequency in hertz.
        """
        if frequency_hz <= 0:
            raise ValueError("channel frequency must be positive")
        config, converter = self._channels[name]
        updated = VirtualChannel(config.name, frequency_hz, config.bandwidth_hz,
                                 config.output_rate_hz)
        converter.reset()
        self._channels[name] = (updated, converter)

    def reset(self) -> None:
        """!
        @brief Discard filter history after a capture gap or hardware retune.

        @param self The current instance.
        """
        for _, converter in self._channels.values():
            converter.reset()

    def process(self, block: IqBlock) -> dict[str, np.ndarray]:
        """!
        @brief Extract all channels from the same raw IQ block.

        Validate every channel before advancing any converter state, so an
        invalid configuration cannot partially consume the shared block.

        @param self The current instance.
        @param block The IQ sample block to process.
        @return The operation result.
        """
        if block.sample_rate_hz != self.input_rate_hz:
            raise ValueError("unexpected source sample rate")
        half_span = self.input_rate_hz / 2
        for config, _ in self._channels.values():
            offset = abs(config.frequency_hz - block.center_frequency_hz)
            if offset + config.bandwidth_hz / 2 >= half_span:
                raise ValueError(
                    f"channel {config.name!r} outside captured RF bandwidth"
                )
        return {
            name: converter.process(block, config.frequency_hz)
            for name, (config, converter) in self._channels.items()
        }
