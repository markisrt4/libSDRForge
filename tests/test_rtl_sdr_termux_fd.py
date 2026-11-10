# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Hardware-free tests for Android USB descriptor selection."""

import ctypes
from unittest.mock import patch

import pytest

from sdrforge.adapters.rtl_sdr import RtlSdrSource


class FakeLibrary:
    def __init__(self):
        self.calls = []

    def rtlsdr_open(self, out, index):
        self.calls.append(("index", index))
        ctypes.cast(out, ctypes.POINTER(ctypes.c_void_p))[0] = 1234
        return 0

    def rtlsdr_open_fd(self, out, fd):
        self.calls.append(("fd", fd))
        ctypes.cast(out, ctypes.POINTER(ctypes.c_void_p))[0] = 1234
        return 0

    def rtlsdr_set_center_freq(self, *_):
        return 0

    def rtlsdr_set_sample_rate(self, *_):
        return 0

    def rtlsdr_set_tuner_gain_mode(self, *_):
        return 0

    def rtlsdr_set_tuner_gain(self, *_):
        return 0

    def rtlsdr_reset_buffer(self, *_):
        return 0

    def rtlsdr_read_sync(self, *_):
        return 0

    def rtlsdr_set_agc_mode(self, *_):
        return 0

    def rtlsdr_close(self, *_):
        return 0


def test_fd_from_termux_environment():
    fake = FakeLibrary()
    with patch.dict("os.environ", {"TERMUX_USB_FD": "7"}):
        source = RtlSdrSource(library=fake)
    source.open()
    assert fake.calls == [("fd", 7)]
    source.close()


def test_linux_uses_device_index():
    fake = FakeLibrary()
    with patch.dict("os.environ", {}, clear=True):
        source = RtlSdrSource(device_index=2, library=fake)
    source.open()
    assert fake.calls == [("index", 2)]
    source.close()


def test_explicit_fd_overrides_environment():
    fake = FakeLibrary()
    with patch.dict("os.environ", {"TERMUX_USB_FD": "7"}):
        source = RtlSdrSource(usb_fd=9, library=fake)
    source.open()
    assert fake.calls == [("fd", 9)]
    source.close()


def test_missing_fd_symbol_fails_clearly():
    fake = FakeLibrary()
    fake.rtlsdr_open_fd = None
    with patch.dict("os.environ", {}, clear=True):
        source = RtlSdrSource(usb_fd=7, library=fake)
    with pytest.raises((RuntimeError, TypeError)):
        source.open()


def test_invalid_environment_fd():
    with patch.dict("os.environ", {"TERMUX_USB_FD": "not-a-number"}):
        with pytest.raises(ValueError, match="TERMUX_USB_FD"):
            RtlSdrSource()
