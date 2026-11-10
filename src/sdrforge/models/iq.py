# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Common types for software-defined radio IQ sources."""

from dataclasses import dataclass
from enum import Enum


class IqSampleFormat(str, Enum):
    """Describe the byte-level representation of IQ samples."""

    U8_INTERLEAVED = "u8_interleaved"


@dataclass(frozen=True)
class SdrCapabilities:
    """Describe tuning and sampling capabilities exposed by an SDR source."""

    min_frequency_hz: int
    max_frequency_hz: int
    supported_sample_rates_hz: tuple[int, ...] = ()
    min_sample_rate_hz: int | None = None
    max_sample_rate_hz: int | None = None
    supports_manual_gain: bool = False


@dataclass(frozen=True)
class IqBlock:
    """A raw IQ block and the RF configuration that produced it.

    timestamp_ns is a monotonic timestamp for the beginning of the block.
    """

    samples: bytes
    center_frequency_hz: int
    sample_rate_hz: int
    timestamp_ns: int
    sample_format: IqSampleFormat = IqSampleFormat.U8_INTERLEAVED
