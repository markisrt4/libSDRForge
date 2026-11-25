# SPDX-License-Identifier: MIT
"""Regression tests for native receiver release evidence."""

import ctypes

import pytest

from sdrforge.adapters.rtl_sdr import RtlSdrSource


class CloseLibrary:
    """Native close result test double."""

    def __init__(self, result: int) -> None:
        self.result = result

    def rtlsdr_close(self, device: ctypes.c_void_p) -> int:
        return self.result


def test_unopened_receiver_is_released() -> None:
    assert RtlSdrSource(usb_fd=3).hardware_released


def test_successful_close_confirms_release() -> None:
    source = RtlSdrSource(library=CloseLibrary(0), usb_fd=3)
    source._device = ctypes.c_void_p(1)
    assert not source.hardware_released
    source.close()
    assert source.hardware_released


def test_failed_close_remains_uncertain() -> None:
    source = RtlSdrSource(library=CloseLibrary(-1), usb_fd=3)
    source._device = ctypes.c_void_p(1)
    with pytest.raises(RuntimeError, match="close device"):
        source.close()
    assert not source.hardware_released
    source.close()
    assert not source.hardware_released
    with pytest.raises(RuntimeError, match="close is unconfirmed"):
        source.open()
