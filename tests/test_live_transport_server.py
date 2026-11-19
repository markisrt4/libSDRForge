"""Hardware-free tests for the live transport controller."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import numpy as np
import pytest


def load_live_server():
    path = Path(__file__).resolve().parents[1] / "examples" / "live_transport_server.py"
    spec = importlib.util.spec_from_file_location("live_transport_server", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_control_mode_validation() -> None:
    module = load_live_server()
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


def test_live_control_start_stop_with_fake_session(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_live_server()
    entered = Event()
    released = Event()

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
            return True

    monkeypatch.setattr(module, "RadioSession", FakeSession)
    stream = FakeStream()
    control = module.LiveRadioControl(stream)
    control.set_muted(True)
    control.start()
    assert entered.is_set()
    released.set()
    control.stop()
    assert control._thread is None
    assert control._error is None
    assert stream.snapshots
    assert stream.snapshots[0]["mode"] == "WFM"
    assert stream.snapshots[0]["bandwidth_hz"] == 200_000
    assert stream.snapshots[0]["frequency_hz"] == 104_300_000
