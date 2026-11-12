"""IQ scanner integration tests with a fake, hardware-free SDR source."""
import numpy as np
import pytest

from sdrforge.adapters.iq_signal_scanner import IqSignalScannerAdapter
from sdrforge.models.iq import IqBlock


class FakeSource:
    def __init__(self) -> None:
        self.frequency = 99_900_000
        self.tunes: list[int] = []
        self.reads = 0
        self.fail = False

    def is_connected(self) -> bool:
        return True

    def get_center_frequency(self) -> int:
        return self.frequency

    def set_center_frequency(self, frequency_hz: int) -> None:
        self.frequency = frequency_hz
        self.tunes.append(frequency_hz)

    def read_iq(self) -> IqBlock:
        self.reads += 1
        if self.fail:
            raise RuntimeError("USB failure")
        count = 4096
        samples = np.arange(count)
        signal = 45 * np.exp(2j * np.pi * 100_000 * samples / 2_400_000)
        raw = np.column_stack((signal.real, signal.imag))
        encoded = np.clip(np.rint(raw + 127.5), 0, 255).astype(np.uint8).tobytes()
        return IqBlock(encoded, self.frequency, 2_400_000, 0)


def test_measurement_restores_frequency() -> None:
    source = FakeSource()
    scanner = IqSignalScannerAdapter(
        source, channel_width_hz=220_000,
        exclusive_access=lambda: True,
    )
    signal, noise = scanner.measure(104_300_000, "WFM")
    assert signal > noise
    assert source.reads == 3
    assert source.tunes == [104_300_000, 99_900_000]


def test_exclusive_ownership_required() -> None:
    source = FakeSource()
    scanner = IqSignalScannerAdapter(source)
    with pytest.raises(RuntimeError, match="exclusive"):
        scanner.measure(104_300_000, "WFM")
    assert source.tunes == []


def test_read_failure_restores_frequency() -> None:
    source = FakeSource()
    source.fail = True
    scanner = IqSignalScannerAdapter(source, exclusive_access=lambda: True)
    with pytest.raises(RuntimeError, match="USB"):
        scanner.measure(104_300_000, "WFM")
    assert source.frequency == 99_900_000


def test_invalid_discard_count() -> None:
    with pytest.raises(ValueError):
        IqSignalScannerAdapter(FakeSource(), discard_blocks=-1)
