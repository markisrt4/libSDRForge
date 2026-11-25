"""Hardware-free tests for the live transport controller."""

from __future__ import annotations

from threading import Event
from types import SimpleNamespace

import numpy as np
import pytest

from sdrforge import live_transport_server as module


def test_live_control_mode_validation() -> None:
    control = module.LiveRadioControl(stream=object())
    assert control.get_frequency() == 104_300_000
    control.set_mode("AM", 25_000)
    assert control.get_mode() == ("AM", 25_000)
    control.set_mode("NFM", 0)
    assert control.get_mode() == ("NFM", 25_000)
    control.set_mode("FM", 0)
    assert control.get_mode() == ("WFM", 200_000)
    control.set_mode("AM", 10_000)
    assert control.get_mode() == ("AM", 10_000)
    with pytest.raises(ValueError, match="bandwidth"):
        control.set_mode("AM", 11_000)
    with pytest.raises(ValueError, match="unsupported radio mode"):
        control.set_mode("SSB", 0)
    with pytest.raises(ValueError, match="positive"):
        control.set_frequency(0)
    control.set_frequency(94_700_000)
    assert control.get_frequency() == 94_700_000


def test_live_control_start_stop_with_fake_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = Event()
    released = Event()
    published = Event()

    class FakeSession:
        def __init__(self, **kwargs: object) -> None:
            self.receiver = type("Receiver", (), {"rds_status": None})()
            self._demodulation = "WFM"
            self.channel_bandwidth_hz = 200_000
            self.frequency_hz = kwargs["frequency_hz"]
            self.stopped = False

        def set_demodulation(self, mode: str, bandwidth: int) -> None:
            self.mode = (mode, bandwidth)
            self._demodulation = mode
            self.channel_bandwidth_hz = bandwidth

        def start(self) -> None:
            entered.set()

        def read(self) -> SimpleNamespace:
            released.wait(timeout=0.01)
            return SimpleNamespace(audio=np.zeros(480, dtype=np.float32))

        def stop(self) -> None:
            self.stopped = True

    class FakeStream:
        def __init__(self) -> None:
            self.snapshots: list[dict[str, object]] = []

        def submit_receiver(self, receiver: object, **kwargs: object) -> bool:
            self.snapshots.append(kwargs)
            published.set()
            return True

    monkeypatch.setattr(module, "RadioSession", FakeSession)
    stream = FakeStream()
    control = module.LiveRadioControl(stream, simulate=True)
    control.set_muted(True)
    control.start()
    assert entered.is_set()
    released.set()
    try:
        assert published.wait(timeout=2)
    finally:
        control.stop()
    assert control._thread is None
    assert control._error is None
    assert stream.snapshots
    assert stream.snapshots[0]["mode"] == "WFM"
    assert stream.snapshots[0]["bandwidth_hz"] == 200_000
    assert stream.snapshots[0]["frequency_hz"] == 104_300_000


def test_audio_sink_mute_remains_responsive_during_blocked_output(monkeypatch) -> None:
    """Blocked device startup must not hold the audio control lock."""
    import sys
    from concurrent.futures import ThreadPoolExecutor

    from sdrforge.adapters.local_audio_sink import LocalAudioSink

    entered = Event()
    release = Event()

    class BlockingStream:
        def __init__(self, **kwargs):
            pass

        def start(self) -> None:
            entered.set()
            assert release.wait(timeout=3), "test did not release device startup"

        def abort(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setitem(
        sys.modules, "sounddevice", SimpleNamespace(OutputStream=BlockingStream)
    )
    sink = LocalAudioSink(sample_rate=100)
    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(sink.write, np.ones((64, 1), dtype=np.float32))
        try:
            assert entered.wait(timeout=2)
            controller = executor.submit(sink.set_muted, True)
            controller.result(timeout=1)
            assert sink.muted is True
            assert sink.diagnostics()["buffer_ms"] == 0
        finally:
            release.set()
        writer.result(timeout=2)
    sink.close()


def test_radio_cleanup_does_not_close_audio_with_blocked_writer() -> None:
    """RF worker shutdown must not close a stream still used by PortAudio."""
    from threading import Event
    from unittest.mock import Mock

    entered = Event()
    release = Event()

    class FakeSession:
        def __init__(self, **kwargs: object) -> None:
            self.receiver = type("Receiver", (), {"rds_status": None})()
            self._demodulation = "WFM"
            self.channel_bandwidth_hz = 200_000
            self.frequency_hz = kwargs["frequency_hz"]

        def set_demodulation(self, mode: str, bandwidth: int) -> None:
            self._demodulation = mode
            self.channel_bandwidth_hz = bandwidth

        def start(self) -> None:
            pass

        def read(self) -> SimpleNamespace:
            entered.set()
            release.wait(timeout=3)
            return SimpleNamespace(audio=np.zeros(480, dtype=np.float32))

        def stop(self) -> None:
            pass

    # The RF worker itself must finish before the audio sink is closed.
    # A separate regression above verifies that audio control remains responsive.
    original = module.RadioSession
    module.RadioSession = FakeSession
    try:
        control = module.LiveRadioControl(stream=Mock(), simulate=True)
        control.audio.close = Mock()
        control.start()
        assert entered.wait(timeout=2)
        release.set()
        control.stop()
        control.audio.close.assert_called_once()
    finally:
        module.RadioSession = original
