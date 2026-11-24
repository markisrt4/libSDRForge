# SPDX-FileCopyrightText: 2026 Mark G. Russell
# SPDX-License-Identifier: MIT

"""Unit tests for the native librtlsdr SDR source."""

import ctypes
import threading
import unittest

from sdrforge.adapters.rtl_sdr import RtlSdrSource


class _Function:
    def __init__(self, implementation):
        self._implementation = implementation
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self._implementation(*args)


class _FakeRtlSdr:
    def __init__(self) -> None:
        self.rtlsdr_open = _Function(self._open)
        self.rtlsdr_close = _Function(lambda _device: 0)
        self.rtlsdr_set_center_freq = _Function(lambda _device, _frequency: 0)
        self.rtlsdr_set_sample_rate = _Function(lambda _device, _rate: 0)
        self.rtlsdr_set_tuner_gain_mode = _Function(lambda _device, _mode: 0)
        self.rtlsdr_set_tuner_gain = _Function(lambda _device, _gain: 0)
        self.rtlsdr_reset_buffer = _Function(lambda _device: 0)
        self.rtlsdr_read_sync = _Function(self._read_sync)

    @staticmethod
    def _open(device_pointer, _index):
        ctypes.cast(device_pointer, ctypes.POINTER(ctypes.c_void_p))[0] = (
            ctypes.c_void_p(0x1234)
        )
        return 0

    @staticmethod
    def _read_sync(_device, buffer, length, bytes_read_pointer):
        payload = bytes((index * 17) & 0xFF for index in range(length))
        ctypes.memmove(buffer, payload, length)
        ctypes.cast(bytes_read_pointer, ctypes.POINTER(ctypes.c_int))[0] = length
        return 0


class RtlSdrSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.library = _FakeRtlSdr()
        self.source = RtlSdrSource(block_bytes=1024, library=self.library)

    def tearDown(self) -> None:
        self.source.close()

    def test_open_configures_default_sample_rate_and_automatic_gain(self) -> None:
        self.source.open()

        self.assertTrue(self.source.is_connected())
        self.assertEqual(self.source.get_sample_rate(), 2_400_000)
        self.assertEqual(len(self.library.rtlsdr_set_sample_rate.calls), 1)
        self.assertEqual(self.library.rtlsdr_set_tuner_gain_mode.calls[-1][1], 0)

    def test_tune_start_and_read_returns_iq_block(self) -> None:
        self.source.open()
        self.source.set_center_frequency(104_300_000)
        self.source.start()

        block = self.source.read_iq()

        self.assertEqual(block.center_frequency_hz, 104_300_000)
        self.assertEqual(block.sample_rate_hz, 2_400_000)
        self.assertEqual(len(block.samples), 1024)
        self.assertGreater(len(set(block.samples)), 1)
        self.assertEqual(len(self.library.rtlsdr_reset_buffer.calls), 1)

    def test_manual_gain_is_converted_to_tenths_of_a_decibel(self) -> None:
        self.source.open()

        self.source.set_gain(19.7)

        self.assertEqual(self.library.rtlsdr_set_tuner_gain_mode.calls[-1][1], 1)
        self.assertEqual(self.library.rtlsdr_set_tuner_gain.calls[-1][1], 197)

    def test_read_requires_started_source_and_frequency(self) -> None:
        self.source.open()
        with self.assertRaisesRegex(RuntimeError, "has not been started"):
            self.source.read_iq()

        self.source.start()
        with self.assertRaisesRegex(RuntimeError, "center frequency"):
            self.source.read_iq()

    def test_disconnected_finished_async_worker_does_not_cancel(self):
        self.library.rtlsdr_cancel_async = _Function(lambda _device: -2)
        self.source.open()
        self.source.set_center_frequency(104_300_000)
        self.source._running = False
        self.source._worker_error = "librtlsdr async read failed: -5"
        worker = threading.Thread(target=lambda: None)
        worker.start()
        worker.join()
        self.source._worker = worker

        self.source.close()

        self.assertFalse(self.source.is_connected())
        self.assertEqual(len(self.library.rtlsdr_cancel_async.calls), 0)
        self.assertEqual(len(self.library.rtlsdr_close.calls), 1)

    def test_cancel_error_still_releases_device_when_worker_has_exited(self):
        self.source.open()
        started = threading.Event()
        release = threading.Event()

        def reader():
            started.set()
            release.wait(timeout=2)

        worker = threading.Thread(target=reader)
        worker.start()
        self.assertTrue(started.wait(timeout=1))
        self.source._worker = worker
        self.source._running = True

        def failed_cancel(_device):
            release.set()
            return -2

        self.library.rtlsdr_cancel_async = _Function(failed_cancel)
        with self.assertRaisesRegex(RuntimeError, "cancel async IQ"):
            self.source.close()
        self.assertFalse(self.source.is_connected())
        self.assertEqual(len(self.library.rtlsdr_close.calls), 1)

    def test_async_disconnect_preserves_error_closes_and_reopens(self) -> None:
        """A failed async USB reader exits, closes, and permits a new session."""
        import time

        failure = -5
        self.library.rtlsdr_read_async = _Function(
            lambda _device, _callback, _ctx, _count, _length: failure
        )
        self.library.rtlsdr_cancel_async = _Function(lambda _device: -2)
        self.source = RtlSdrSource(
            block_bytes=1024, library=self.library, acquisition_mode="async"
        )
        self.source.open()
        self.source.set_center_frequency(104_300_000)
        self.source.start()
        deadline = time.monotonic() + 2
        while self.source._worker is not None and self.source._worker.is_alive():
            if time.monotonic() > deadline:
                self.fail("async reader did not exit after USB failure")
            time.sleep(0.01)
        with self.assertRaisesRegex(RuntimeError, "async read failed: -5"):
            self.source.read_iq()
        self.source.close()
        self.assertFalse(self.source.is_connected())
        self.assertEqual(len(self.library.rtlsdr_cancel_async.calls), 0)
        self.assertEqual(len(self.library.rtlsdr_close.calls), 1)
        self.assertEqual(self.source._worker_error, "librtlsdr async read failed: -5")

        # A reattached device can be reopened and read using synchronous mode.
        self.source = RtlSdrSource(
            block_bytes=1024, library=self.library, acquisition_mode="sync"
        )
        self.source.open()
        self.source.set_center_frequency(104_300_000)
        self.source.start()
        block = self.source.read_iq()
        self.assertEqual(len(block.samples), 1024)
        self.source.close()
        self.assertEqual(len(self.library.rtlsdr_open.calls), 2)

    def test_sync_usb_read_failure_can_close_and_reopen(self) -> None:
        """A failed USB read must not prevent closing and reopening the handle."""
        self.source.open()
        self.source.set_center_frequency(104_300_000)
        self.source.start()
        self.library.rtlsdr_read_sync = _Function(
            lambda _device, _buffer, _length, _read: -5
        )

        with self.assertRaisesRegex(RuntimeError, "read IQ: error -5"):
            self.source.read_iq()

        self.source.close()
        self.assertFalse(self.source.is_connected())
        self.assertEqual(len(self.library.rtlsdr_close.calls), 1)

        self.library.rtlsdr_read_sync = _Function(self.library._read_sync)
        self.source.open()
        self.source.set_center_frequency(104_300_000)
        self.source.start()
        block = self.source.read_iq()
        self.assertEqual(len(block.samples), 1024)
        self.assertEqual(len(self.library.rtlsdr_open.calls), 2)

    def test_librtlsdr_errors_are_not_silently_ignored(self) -> None:
        self.library.rtlsdr_set_center_freq = _Function(lambda _device, _frequency: -5)
        self.source.open()

        with self.assertRaisesRegex(RuntimeError, "error -5"):
            self.source.set_center_frequency(104_300_000)


if __name__ == "__main__":
    unittest.main()
