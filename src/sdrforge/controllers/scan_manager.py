"""Cancelable, hardware-neutral stepped frequency discovery."""
from collections.abc import Callable
from threading import Event

from sdrforge.interfaces.signal_scanner import SignalScannerIf
from sdrforge.models.discovered_station import DiscoveredStation
from sdrforge.models.scan_config import ScanConfig


class ScanManager:
    def __init__(self, scanner: SignalScannerIf) -> None:
        self.scanner = scanner

    def scan(
        self,
        config: ScanConfig,
        *,
        cancel: Event | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> list[DiscoveredStation]:
        total = (config.stop_hz - config.start_hz) // config.step_hz + 1
        discovered: list[DiscoveredStation] = []
        for index in range(total):
            if cancel is not None and cancel.is_set():
                break
            frequency = config.start_hz + index * config.step_hz
            signal, noise = self.scanner.measure(frequency, config.modulation)
            if signal - noise >= config.threshold_db:
                discovered.append(
                    DiscoveredStation(frequency, config.modulation, signal, noise),
                )
            if progress is not None:
                progress(index + 1, total)
        return discovered
