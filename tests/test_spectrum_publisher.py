# SPDX-License-Identifier: MIT
"""Synthetic IQ tests for rate limiting and bounded frame delivery."""
import numpy as np
import pytest

from sdrforge.controllers.spectrum_publisher import SpectrumPublisher


def _iq(size: int = 128) -> np.ndarray:
    return np.exp(2j * np.pi * 7 * np.arange(size) / size)


def test_rate_limit_and_latest_frame() -> None:
    publisher = SpectrumPublisher(fft_size=128, max_fps=10)
    subscriber = publisher.subscribe(max_frames=2)
    assert publisher.publish_iq(_iq(), center_frequency_hz=100_000_000,
                                sample_rate_hz=1_280_000, timestamp_ns=0) is not None
    assert publisher.publish_iq(_iq(), center_frequency_hz=100_000_000,
                                sample_rate_hz=1_280_000, timestamp_ns=50_000_000) is None
    assert publisher.publish_iq(_iq(), center_frequency_hz=101_000_000,
                                sample_rate_hz=1_280_000, timestamp_ns=100_000_000) is not None
    latest = subscriber.poll_latest()
    assert latest is not None
    assert latest.center_frequency_hz == 101_000_000
    assert subscriber.poll() is None


def test_bounded_queue_discards_oldest() -> None:
    publisher = SpectrumPublisher(fft_size=128, max_fps=10)
    subscriber = publisher.subscribe(max_frames=2)
    for tick in range(4):
        publisher.publish_iq(_iq(), center_frequency_hz=100_000_000,
                             sample_rate_hz=1_280_000, timestamp_ns=tick * 100_000_000)
    first = subscriber.poll()
    second = subscriber.poll()
    assert first is not None and first.timestamp_ns == 200_000_000
    assert second is not None and second.timestamp_ns == 300_000_000
    assert subscriber.poll() is None


def test_unsubscribe_and_reset() -> None:
    publisher = SpectrumPublisher(fft_size=128, max_fps=10)
    subscriber = publisher.subscribe()
    publisher.publish_iq(_iq(), center_frequency_hz=100_000_000,
                         sample_rate_hz=1_280_000, timestamp_ns=100)
    publisher.unsubscribe(subscriber)
    assert subscriber.poll() is None
    publisher.reset()
    assert publisher.publish_iq(_iq(), center_frequency_hz=100_000_000,
                                sample_rate_hz=1_280_000, timestamp_ns=100) is not None


def test_invalid_configuration_and_short_iq() -> None:
    with pytest.raises(ValueError):
        SpectrumPublisher(max_fps=0)
    publisher = SpectrumPublisher(fft_size=128)
    with pytest.raises(ValueError, match="shorter"):
        publisher.publish_iq(_iq(64), center_frequency_hz=100_000_000,
                             sample_rate_hz=1_280_000, timestamp_ns=0)


def test_latest_snapshot_does_not_consume_subscriptions() -> None:
    publisher = SpectrumPublisher(fft_size=128)
    first = publisher.subscribe(max_frames=2)
    second = publisher.subscribe(max_frames=2)
    assert publisher.latest_frame() is None
    published = publisher.publish_iq(
        _iq(), center_frequency_hz=104_300_000,
        sample_rate_hz=1_280_000, timestamp_ns=123,
    )
    assert published is not None
    assert publisher.latest_frame() is published
    assert publisher.latest_frame() is published
    assert first.poll_latest() is published
    assert second.poll_latest() is published
