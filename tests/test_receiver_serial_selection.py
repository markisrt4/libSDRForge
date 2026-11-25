# SPDX-License-Identifier: MIT
"""Tests for explicit RTL-SDR serial selection."""

import ctypes

import pytest

from sdrforge.adapters.rtl_sdr import RtlSdrSource


class SerialLibrary:
    """Minimal librtlsdr identity API double."""

    def __init__(self, serials: list[bytes], opened: bytes = b"second") -> None:
        self.serials = serials
        self.opened = opened

    def rtlsdr_get_device_count(self) -> int:
        return len(self.serials)

    def rtlsdr_get_device_usb_strings(self, index, manufacturer, product, serial):
        serial.value = self.serials[index]
        return 0

    def rtlsdr_get_usb_strings(self, device, manufacturer, product, serial):
        serial.value = self.opened
        return 0


def test_resolve_unique_serial() -> None:
    library = SerialLibrary([b"first", b"second"])
    assert RtlSdrSource._resolve_serial(library, "second") == 1
    library.serials.reverse()
    assert RtlSdrSource._resolve_serial(library, "second") == 0


@pytest.mark.parametrize("serials", [[], [b"first"], [b"second", b"second"]])
def test_reject_missing_or_ambiguous_serial(serials: list[bytes]) -> None:
    with pytest.raises(RuntimeError, match="missing or ambiguous"):
        RtlSdrSource._resolve_serial(SerialLibrary(serials), "second")


def test_verify_opened_serial() -> None:
    RtlSdrSource._verify_serial(SerialLibrary([]), ctypes.c_void_p(1), "second")


def test_reject_changed_opened_identity() -> None:
    with pytest.raises(RuntimeError, match="does not match"):
        RtlSdrSource._verify_serial(
            SerialLibrary([], opened=b"first"), ctypes.c_void_p(1), "second"
        )


def test_serial_conflicts_with_usb_fd() -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        RtlSdrSource(usb_fd=3, device_serial="second")


def test_usb_fd_remains_supported() -> None:
    assert RtlSdrSource(usb_fd=3)._usb_fd == 3


def test_reject_empty_serial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TERMUX_USB_FD", raising=False)
    with pytest.raises(ValueError, match="nonempty"):
        RtlSdrSource(device_serial=" ")
