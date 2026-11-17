"""Hardware-free tests for the live transport controller."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from threading import Event

import pytest


def load_live_server():
    path = Path(__file__).resolve().parents[1] / "examples" / "live_transport_server.py"
    spec = importlib.util.spec_from_file_location("live_transport_server", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_control_requires_wfm() -> None:
    module = load_live_server()
    control = module.LiveRadioControl(stream=object())
    assert control.get_frequency() == 104_300_000
    with pytest.raises(ValueError, match="WFM"):
        control.set_mode("AM", 10000)
    with pytest.raises(ValueError, match="positive"):
        control.set_frequency(0)
    control.set_frequency(94_700_000)
    assert control.get_frequency() == 94_700_000


def test_live_control_start_stop_with_fake_session(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_live_server()
    entered = Event()
    released = Event()

    class FakeSession:
        def __init__(self, **kwargs: object) -> None:
            self.receiver = type("Receiver", (), {"rds_status": None})()
            self.stopped = False

        def start(self) -> None:
            entered.set()

        def read(self) -> object:
            released.wait(timeout=0.01)
            return type("Frame", (), {"audio": None})()

        def stop(self) -> None:
            self.stopped = True

    class FakeStream:
        def submit_receiver(self, receiver: object) -> bool:
            return True

    monkeypatch.setattr(module, "RadioSession", FakeSession)
    control = module.LiveRadioControl(FakeStream())
    control.start()
    assert entered.is_set()
    released.set()
    control.stop()
    assert control._thread is None



def test_audio_sink_mute_remains_responsive_during_blocked_output() -> None:
    """A blocked PortAudio write must not hold the audio control lock."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    import numpy as np

    from sdrforge.adapters.local_audio_sink import LocalAudioSink

    entered = Event()
    release = Event()

    class BlockingStream:
        def write(self, audio: object) -> None:
            entered.set()
            assert release.wait(timeout=3), "test did not release blocked writer"

    sink = LocalAudioSink()
    sink._stream = BlockingStream()
    sink._channels = 1
    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(sink.write, np.ones((64, 1), dtype=np.float32))
        try:
            assert entered.wait(timeout=2)
            controller = executor.submit(sink.set_muted, True)
            controller.result(timeout=1)
            assert sink.muted is True
        finally:
            release.set()
        writer.result(timeout=2)


def test_radio_cleanup_does_not_close_audio_with_blocked_writer() -> None:
    """RF worker shutdown must not close a stream still used by PortAudio."""
    from threading import Event
    from unittest.mock import Mock

    module = load_live_server()
    entered = Event()
    release = Event()

    class FakeSession:
        def __init__(self, **kwargs: object) -> None:
            self.receiver = object()

        def start(self) -> None:
            pass

        def read(self) -> object:
            entered.set()
            release.wait(timeout=3)
            return type("Frame", (), {"audio": None})()

        def stop(self) -> None:
            pass

    # The RF worker itself must finish before the audio sink is closed.
    # A separate regression above verifies that audio control remains responsive.
    original = module.RadioSession
    module.RadioSession = FakeSession
    try:
        control = module.LiveRadioControl(stream=Mock())
        control.audio.close = Mock()
        control.start()
        assert entered.wait(timeout=2)
        release.set()
        control.stop()
        control.audio.close.assert_called_once()
    finally:
        module.RadioSession = original
